import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";

/** GET /api/admin/transcripts — list all transcripts (lightweight, no segments) */
export async function GET(req: NextRequest) {
  try {
    const searchParams = req.nextUrl.searchParams;
    const sortField = searchParams.get("sort") || "event_date";
    const sortDir = searchParams.get("dir") === "asc" ? "asc" : "desc";

    const allowedSorts: Record<string, string> = {
      event_date: "event_date",
      title: "title",
      primary_speaker: "primary_speaker",
      speech_type: "speech_type",
      created_at: "created_at",
    };

    const orderBy: Record<string, string> = {};
    orderBy[allowedSorts[sortField] || "event_date"] = sortDir;

    const transcripts = await prisma.transcript.findMany({
      orderBy,
      select: {
        id: true,
        title: true,
        event_date: true,
        speech_type: true,
        primary_speaker: true,
        speakers_present: true,
        has_q_and_a: true,
        total_speech_length_seconds: true,
        key_themes: true,
        created_at: true,
        _count: { select: { segments: true } },
      },
    });

    return NextResponse.json({ transcripts });
  } catch (err) {
    console.error("List transcripts error:", err);
    return NextResponse.json({ error: "Server error" }, { status: 500 });
  }
}

/** POST /api/admin/transcripts — create a new transcript + segments */
export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const {
      title,
      event_date,
      speech_type,
      primary_speaker,
      speakers_present,
      has_q_and_a,
      total_speech_length_seconds,
      key_themes,
      segments,
      question_count,
      avg_response_length_words,
      avg_response_length_seconds,
      qa_data,
      qa_data_auto,
      qa_overrides,
      // Earnings call metadata (optional)
      company_ticker,
      fiscal_year,
      fiscal_quarter,
      source,
      source_url,
      earnings_key,
    } = body;

    // Validate required fields
    if (!title || !event_date || !speech_type || !primary_speaker) {
      return NextResponse.json(
        { error: "Missing required fields: title, event_date, speech_type, primary_speaker" },
        { status: 400 }
      );
    }

    if (!segments || !Array.isArray(segments) || segments.length === 0) {
      return NextResponse.json(
        { error: "At least one segment is required" },
        { status: 400 }
      );
    }

    const transcriptData = {
      title,
      event_date: new Date(event_date),
      speech_type,
      primary_speaker,
      speakers_present: speakers_present || [],
      has_q_and_a: has_q_and_a || false,
      total_speech_length_seconds: total_speech_length_seconds || null,
      key_themes: key_themes || [],
      question_count: question_count || null,
      avg_response_length_words: avg_response_length_words || null,
      avg_response_length_seconds: avg_response_length_seconds || null,
      qa_data: qa_data || null,
      qa_data_auto: qa_data_auto || null,
      qa_overrides: qa_overrides || null,
      company_ticker: company_ticker || null,
      fiscal_year: fiscal_year || null,
      fiscal_quarter: fiscal_quarter || null,
      source: source || null,
      source_url: source_url || null,
      earnings_key: earnings_key || null,
    };

    // For earnings calls: use upsert keyed on earnings_key or source_url so
    // re-runs are idempotent and update existing records rather than failing.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const upsertWhere: any = earnings_key
      ? { earnings_key }
      : source_url
        ? { source_url }
        : null;

    const transcript = await prisma.$transaction(async (tx) => {
      const t = upsertWhere
        ? await tx.transcript.upsert({
            where: upsertWhere,
            create: transcriptData,
            update: transcriptData,
            select: { id: true },
          })
        : await tx.transcript.create({
            data: transcriptData,
            select: { id: true },
          });

      // Replace segments (delete + re-insert)
      await tx.speakingSegment.deleteMany({ where: { transcriptId: t.id } });
      await tx.speakingSegment.createMany({
        data: segments.map(
          (seg: {
            speaker: string;
            start_seconds: number;
            end_seconds?: number | null;
            text: string;
          }) => ({
            transcriptId: t.id,
            speaker: seg.speaker,
            start_seconds: seg.start_seconds,
            end_seconds: seg.end_seconds ?? null,
            text: seg.text,
          })
        ),
      });

      return t;
    });

    return NextResponse.json({ id: transcript.id }, { status: 201 });
  } catch (err) {
    console.error("Create transcript error:", err);
    return NextResponse.json({ error: "Server error" }, { status: 500 });
  }
}

