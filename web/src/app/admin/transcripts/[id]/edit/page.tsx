import { notFound } from "next/navigation";
import { prisma } from "@/lib/db";
import { EditTranscriptClient } from "./EditClient";

export const dynamic = "force-dynamic";

export default async function EditTranscriptPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  let transcript;
  try {
    transcript = await prisma.transcript.findUnique({
      where: { id },
      include: { segments: { orderBy: { start_seconds: "asc" } } },
    });
  } catch {
    transcript = null;
  }

  if (!transcript) notFound();

  // Serialize for client component
  const data = {
    id: transcript.id,
    title: transcript.title,
    event_date: transcript.event_date.toISOString().slice(0, 10),
    speech_type: transcript.speech_type,
    primary_speaker: transcript.primary_speaker,
    speakers_present: transcript.speakers_present,
    has_q_and_a: transcript.has_q_and_a,
    total_speech_length_seconds: transcript.total_speech_length_seconds,
    key_themes: transcript.key_themes,
    segments: transcript.segments.map((s) => ({
      speaker: s.speaker,
      start_seconds: s.start_seconds,
      end_seconds: s.end_seconds,
      text: s.text,
    })),
    // Pass Q&A curation state so the editor reflects prior user edits
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    qa_data: (transcript.qa_data as any) ?? null,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    qa_data_auto: (transcript.qa_data_auto as any) ?? null,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    qa_overrides: (transcript.qa_overrides as any) ?? null,
  };

  return <EditTranscriptClient data={data} />;
}

