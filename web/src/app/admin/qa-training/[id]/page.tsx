import { notFound } from "next/navigation";
import { prisma } from "@/lib/db";
import { extractCandidateExchanges } from "@/lib/parsers/otter";
import { LabelingClient } from "./LabelingClient";

export const dynamic = "force-dynamic";

interface Props {
  params: Promise<{ id: string }>;
}

export default async function QATrainingTranscriptPage({ params }: Props) {
  const { id } = await params;

  const transcript = await prisma.transcript.findUnique({
    where: { id },
    select: {
      id: true,
      title: true,
      primary_speaker: true,
      has_q_and_a: true,
      segments: {
        select: {
          speaker: true,
          start_seconds: true,
          end_seconds: true,
          text: true,
        },
        orderBy: { start_seconds: "asc" },
      },
    },
  });

  if (!transcript) notFound();

  const existingLabels = await prisma.qALabel.findMany({
    where: { transcriptId: id },
    select: {
      id: true,
      questionText: true,
      isQA: true,
      reasoning: true,
    },
    orderBy: { created_at: "asc" },
  });

  const candidates = extractCandidateExchanges(
    transcript.segments,
    transcript.primary_speaker
  );

  return (
    <div className="mx-auto max-w-2xl">
      <LabelingClient
        transcriptId={transcript.id}
        transcriptTitle={transcript.title}
        primarySpeaker={transcript.primary_speaker}
        candidates={candidates}
        existingLabels={existingLabels}
      />
    </div>
  );
}
