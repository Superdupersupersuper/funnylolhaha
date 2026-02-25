"use client";

import { TranscriptForm } from "@/components/admin/TranscriptForm";
import type { ParsedSegment, QAPair } from "@/lib/parsers/otter";

interface EditTranscriptClientProps {
  data: {
    id: string;
    title: string;
    event_date: string;
    speech_type: string;
    primary_speaker: string;
    speakers_present: string[];
    has_q_and_a: boolean;
    total_speech_length_seconds: number | null;
    key_themes: string[];
    segments: ParsedSegment[];
    qa_data?: QAPair[] | null;
    qa_data_auto?: QAPair[] | null;
    qa_overrides?: { removedKeys: string[] } | null;
  };
}

export function EditTranscriptClient({ data }: EditTranscriptClientProps) {
  return <TranscriptForm initialData={data} />;
}

