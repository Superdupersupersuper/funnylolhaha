import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";

/**
 * GET /api/search?q=keyword&speaker=X&theme=Y&has_qa=true&start=YYYY-MM-DD&end=YYYY-MM-DD&limit=50&offset=0
 *
 * Searches across SpeakingSegment.text (case-insensitive contains),
 * with filters on the parent Transcript, then aggregates results
 * by transcript.
 *
 * Only segments spoken by the transcript's primary_speaker contribute
 * to mentionCount / totalMentions. Other-speaker matches are still
 * returned (with isPrimary=false) for context display.
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
            speakers_present: true,
            key_themes: true,
            has_q_and_a: true,
            total_speech_length_seconds: true,
            company_ticker: true,
            fiscal_year: true,
            fiscal_quarter: true,
          },
        },
      },
      orderBy: [
        { transcript: { event_date: "desc" } },
        { start_seconds: "asc" },
      ],
    });

    // Aggregate by transcript
    type SegmentEntry = {
      speaker: string;
      start_seconds: number;
      text: string;
      highlighted: string;
      isPrimary: boolean;
    };
    const transcriptMap = new Map<
      string,
      {
        transcript: (typeof matchingSegments)[0]["transcript"];
        mentionCount: number;
        segments: SegmentEntry[];
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

      // For earnings calls: "primary" means any company representative
      // (stored in speakers_present). For other transcripts: match primary_speaker only.
      const isEarningsCall = seg.transcript.speech_type === "Earnings Call";
      const selectedSpeaker = speaker || seg.transcript.primary_speaker;
      const isPrimary = isEarningsCall
        ? seg.transcript.speakers_present.some((s) =>
            speakerMatchesPrimary(seg.speaker, s)
          )
        : speakerMatchesPrimary(seg.speaker, selectedSpeaker);

      // Count only primary-speaker occurrences
      const regex = new RegExp(escapeRegex(q), "gi");
      const matches = seg.text.match(regex);
      const count = matches ? matches.length : 1;
      if (isPrimary) {
        entry.mentionCount += count;
      }

      // Highlight: blue <mark> for primary, orange <mark class="other"> for non-primary
      const highlighted = isPrimary
        ? seg.text.replace(regex, "<mark>$&</mark>")
        : seg.text.replace(regex, '<mark class="other">$&</mark>');

      entry.segments.push({
        speaker: seg.speaker,
        start_seconds: seg.start_seconds,
        text: seg.text,
        highlighted,
        isPrimary,
      });
    }

    // Only keep transcripts where the primary speaker has at least one mention
    const allResults = Array.from(transcriptMap.values()).filter(
      (r) => r.mentionCount > 0
    );
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

/**
 * Case-insensitive, punctuation-stripped comparison.
 * Returns true when one name contains the other (handles
 * "Donald Trump" vs "Donald J. Trump", "J.D. Vance" vs "Vance", "Zohran Mamdani" vs "Mamdani", etc.)
 */
function speakerMatchesPrimary(
  sectionSpeaker: string,
  primarySpeaker: string
): boolean {
  if (!sectionSpeaker || !primarySpeaker) return false;
  const norm = (s: string) =>
    s
      .toLowerCase()
      .replace(/[^a-z\s]/g, "")
      .replace(/\s+/g, " ")
      .trim();
  const a = norm(sectionSpeaker);
  const b = norm(primarySpeaker);
  if (!a || !b) return false;

  // Exact match
  if (a === b) return true;

  // Also allow matches that differ only by spacing (e.g. "mrbeast" vs "mr beast")
  const aNoSpace = a.replace(/\s/g, "");
  const bNoSpace = b.replace(/\s/g, "");
  if (
    aNoSpace &&
    bNoSpace &&
    (aNoSpace === bNoSpace ||
      aNoSpace.includes(bNoSpace) ||
      bNoSpace.includes(aNoSpace))
  ) {
    return true;
  }

  // Split into words for more robust matching
  const aWords = a.split(" ").filter((w) => w.length > 0);
  const bWords = b.split(" ").filter((w) => w.length > 0);

  // If either contains all words of the other, it's a match
  const aContainsAllB = bWords.every((w) => aWords.includes(w));
  const bContainsAllA = aWords.every((w) => bWords.includes(w));

  return aContainsAllB || bContainsAllA;
}
