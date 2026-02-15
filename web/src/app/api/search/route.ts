import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";

/**
 * GET /api/search?q=keyword&speaker=X&theme=Y&has_qa=true&start=YYYY-MM-DD&end=YYYY-MM-DD&limit=50&offset=0
 *
 * Searches across SpeakingSegment.text (case-insensitive contains),
 * with filters on the parent Transcript, then aggregates results
 * by transcript (mention count + first match context).
 */
export async function GET(req: NextRequest) {
  try {
    const sp = req.nextUrl.searchParams;
    const q = sp.get("q")?.trim();
    const speaker = sp.get("speaker")?.trim();
    const theme = sp.get("theme")?.trim();
    const hasQA = sp.get("has_qa");
    const startDate = sp.get("start");
    const endDate = sp.get("end");
    const limit = Math.min(Number(sp.get("limit")) || 50, 200);
    const offset = Number(sp.get("offset")) || 0;

    if (!q) {
      return NextResponse.json(
        { error: "Query parameter 'q' is required" },
        { status: 400 }
      );
    }

    // Build the where clause on segments joined with transcript filters
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const transcriptWhere: Record<string, any> = {};

    if (speaker) {
      transcriptWhere.primary_speaker = { contains: speaker, mode: "insensitive" };
    }
    if (theme) {
      transcriptWhere.key_themes = { has: theme };
    }
    if (hasQA === "true") {
      transcriptWhere.has_q_and_a = true;
    }
    if (startDate) {
      transcriptWhere.event_date = {
        ...transcriptWhere.event_date,
        gte: new Date(startDate),
      };
    }
    if (endDate) {
      transcriptWhere.event_date = {
        ...transcriptWhere.event_date,
        lte: new Date(endDate),
      };
    }

    // Find matching segments
    const matchingSegments = await prisma.speakingSegment.findMany({
      where: {
        text: { contains: q, mode: "insensitive" },
        transcript: transcriptWhere,
      },
      include: {
        transcript: {
          select: {
            id: true,
            title: true,
            event_date: true,
            speech_type: true,
            primary_speaker: true,
            key_themes: true,
            has_q_and_a: true,
            total_speech_length_seconds: true,
          },
        },
      },
      orderBy: [
        { transcript: { event_date: "desc" } },
        { start_seconds: "asc" },
      ],
    });

    // Aggregate by transcript
    const transcriptMap = new Map<
      string,
      {
        transcript: (typeof matchingSegments)[0]["transcript"];
        mentionCount: number;
        segments: {
          speaker: string;
          start_seconds: number;
          text: string;
          highlighted: string;
        }[];
      }
    >();

    for (const seg of matchingSegments) {
      const tid = seg.transcript.id;
      if (!transcriptMap.has(tid)) {
        transcriptMap.set(tid, {
          transcript: seg.transcript,
          mentionCount: 0,
          segments: [],
        });
      }
      const entry = transcriptMap.get(tid)!;

      // Count all case-insensitive occurrences in this segment
      const regex = new RegExp(escapeRegex(q), "gi");
      const matches = seg.text.match(regex);
      entry.mentionCount += matches ? matches.length : 1;

      // Simple highlight: wrap matches in <mark>
      const highlighted = seg.text.replace(regex, "<mark>$&</mark>");

      entry.segments.push({
        speaker: seg.speaker,
        start_seconds: seg.start_seconds,
        text: seg.text,
        highlighted,
      });
    }

    // Convert to array + paginate at transcript level
    const allResults = Array.from(transcriptMap.values());
    const paginated = allResults.slice(offset, offset + limit);

    return NextResponse.json({
      query: q,
      totalTranscripts: allResults.length,
      totalMentions: allResults.reduce((s, r) => s + r.mentionCount, 0),
      results: paginated,
    });
  } catch (err) {
    console.error("Search error:", err);
    return NextResponse.json({ error: "Server error" }, { status: 500 });
  }
}

function escapeRegex(str: string) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

