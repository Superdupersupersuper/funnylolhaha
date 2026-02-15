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
  };

  return <EditTranscriptClient data={data} />;
}

