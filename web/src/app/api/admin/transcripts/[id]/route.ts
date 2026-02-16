import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";

/** GET /api/admin/transcripts/:id — get single transcript with all segments */
export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;

    const transcript = await prisma.transcript.findUnique({
      where: { id },
      include: {
        segments: { orderBy: { start_seconds: "asc" } },
      },
    });

    if (!transcript) {
      return NextResponse.json({ error: "Not found" }, { status: 404 });
    }

    return NextResponse.json({ transcript });
  } catch (err) {
    console.error("Get transcript error:", err);
    return NextResponse.json({ error: "Server error" }, { status: 500 });
  }
}

/** PUT /api/admin/transcripts/:id — update transcript metadata + replace segments */
export async function PUT(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
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
    } = body;

    // Update in a transaction: update transcript, delete old segments, insert new
    const transcript = await prisma.$transaction(async (tx) => {
      const t = await tx.transcript.update({
        where: { id },
        data: {
          title,
          event_date: event_date ? new Date(event_date) : undefined,
          speech_type,
          primary_speaker,
          speakers_present: speakers_present || [],
          has_q_and_a: has_q_and_a ?? false,
          total_speech_length_seconds: total_speech_length_seconds ?? null,
          key_themes: key_themes || [],
          question_count: question_count ?? null,
          avg_response_length_words: avg_response_length_words ?? null,
          avg_response_length_seconds: avg_response_length_seconds ?? null,
          qa_data: qa_data ?? null,
        },
      });

      if (segments && Array.isArray(segments)) {
        // Delete all existing segments and re-insert
        await tx.speakingSegment.deleteMany({ where: { transcriptId: id } });
        await tx.speakingSegment.createMany({
          data: segments.map(
            (seg: {
              speaker: string;
              start_seconds: number;
              end_seconds?: number | null;
              text: string;
            }) => ({
              transcriptId: id,
              speaker: seg.speaker,
              start_seconds: seg.start_seconds,
              end_seconds: seg.end_seconds ?? null,
              text: seg.text,
            })
          ),
        });
      }

      return t;
    });

    return NextResponse.json({ id: transcript.id });
  } catch (err) {
    console.error("Update transcript error:", err);
    return NextResponse.json({ error: "Server error" }, { status: 500 });
  }
}

/** DELETE /api/admin/transcripts/:id — delete transcript (cascades to segments) */
export async function DELETE(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;

    await prisma.transcript.delete({ where: { id } });

    return NextResponse.json({ ok: true });
  } catch (err) {
    console.error("Delete transcript error:", err);
    return NextResponse.json({ error: "Server error" }, { status: 500 });
  }
}

