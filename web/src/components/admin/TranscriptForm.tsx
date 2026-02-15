"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { parseOtterTranscript, type ParseResult, type ParsedSegment } from "@/lib/parsers/otter";
import { TagInput } from "./TagInput";
import { SegmentPreview } from "./SegmentPreview";

const SPEECH_TYPES = [
  "Remarks",
  "Press Conference",
  "Interview",
  "Rally",
  "Press Briefing",
  "Sports Commentary",
  "Earnings Call",
  "Other",
];

interface TranscriptFormProps {
  /** If provided, we're in edit mode. */
  initialData?: {
    id: string;
    title: string;
    event_date: string; // YYYY-MM-DD
    speech_type: string;
    primary_speaker: string;
    speakers_present: string[];
    has_q_and_a: boolean;
    total_speech_length_seconds: number | null;
    key_themes: string[];
    segments: ParsedSegment[];
    raw_text?: string;
  };
}

export function TranscriptForm({ initialData }: TranscriptFormProps) {
  const router = useRouter();
  const isEdit = !!initialData;

  // Form fields
  const [title, setTitle] = useState(initialData?.title ?? "");
  const [eventDate, setEventDate] = useState(initialData?.event_date ?? "");
  const [speechType, setSpeechType] = useState(initialData?.speech_type ?? "");
  const [customSpeechType, setCustomSpeechType] = useState("");
  const [primarySpeaker, setPrimarySpeaker] = useState(
    initialData?.primary_speaker ?? ""
  );
  const [speakersPresent, setSpeakersPresent] = useState<string[]>(
    initialData?.speakers_present ?? []
  );
  const [hasQAndA, setHasQAndA] = useState(initialData?.has_q_and_a ?? false);
  const [totalLength, setTotalLength] = useState<number | "">(
    initialData?.total_speech_length_seconds ?? ""
  );
  const [keyThemes, setKeyThemes] = useState<string[]>(
    initialData?.key_themes ?? []
  );

  // Raw text + parsing
  const [rawText, setRawText] = useState(initialData?.raw_text ?? "");
  const [parseResult, setParseResult] = useState<ParseResult | null>(null);
  const [segments, setSegments] = useState<ParsedSegment[]>(
    initialData?.segments ?? []
  );

  // UI state
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [deleting, setDeleting] = useState(false);

  // Parse the raw text
  const handleParse = useCallback(() => {
    if (!rawText.trim()) return;
    const result = parseOtterTranscript(rawText);
    setParseResult(result);
    setSegments(result.segments);

    // Auto-fill fields from parse result
    if (result.calculated.suggestedPrimarySpeaker && !primarySpeaker) {
      setPrimarySpeaker(result.calculated.suggestedPrimarySpeaker);
    }
    if (result.calculated.speakersDetected.length > 0 && speakersPresent.length === 0) {
      setSpeakersPresent(result.calculated.speakersDetected);
    }
    if (result.calculated.totalSeconds && !totalLength) {
      setTotalLength(Math.round(result.calculated.totalSeconds));
    }
  }, [rawText, primarySpeaker, speakersPresent.length, totalLength]);

  // Handle file upload
  async function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    setRawText(text);

    // Auto-set title from filename if empty
    if (!title) {
      const name = file.name
        .replace(/_otter_ai\.txt$/i, "")
        .replace(/\.(txt|srt)$/i, "")
        .replace(/_/g, " ");
      setTitle(name);
    }
  }

  // Save
  async function handleSave() {
    setError("");
    if (!title || !eventDate || !primarySpeaker) {
      setError("Title, event date, and primary speaker are required.");
      return;
    }
    if (segments.length === 0) {
      setError("Parse the transcript first — no segments found.");
      return;
    }

    const resolvedSpeechType =
      speechType === "Other" ? customSpeechType || "Other" : speechType || "Other";

    const payload = {
      title,
      event_date: eventDate,
      speech_type: resolvedSpeechType,
      primary_speaker: primarySpeaker,
      speakers_present: speakersPresent,
      has_q_and_a: hasQAndA,
      total_speech_length_seconds: totalLength || null,
      key_themes: keyThemes,
      segments: segments.map((s) => ({
        speaker: s.speaker,
        start_seconds: s.start_seconds,
        end_seconds: s.end_seconds,
        text: s.text,
      })),
    };

    setSaving(true);
    try {
      const url = isEdit
        ? `/api/admin/transcripts/${initialData!.id}`
        : "/api/admin/transcripts";
      const method = isEdit ? "PUT" : "POST";

      const res = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setError(data.error || "Failed to save");
        return;
      }

      router.push("/admin/transcripts");
      router.refresh();
    } catch {
      setError("Network error");
    } finally {
      setSaving(false);
    }
  }

  // Delete (edit mode only)
  async function handleDelete() {
    if (!isEdit) return;
    if (!confirm("Are you sure you want to delete this transcript? This cannot be undone.")) return;

    setDeleting(true);
    try {
      const res = await fetch(`/api/admin/transcripts/${initialData!.id}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        setError("Failed to delete");
        return;
      }
      router.push("/admin/transcripts");
      router.refresh();
    } catch {
      setError("Network error");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">
        {isEdit ? "Edit Transcript" : "Upload New Transcript"}
      </h1>

      {error && (
        <div className="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* ─── Raw text input ─── */}
      <div className="rounded-lg border border-border bg-card p-4 space-y-3">
        <h2 className="text-sm font-semibold">1. Paste or Upload Otter Transcript</h2>
        <div className="flex items-center gap-3">
          <label className="cursor-pointer rounded-md border border-input bg-background px-3 py-1.5 text-sm hover:bg-accent">
            Choose File (.txt, .srt)
            <input
              type="file"
              accept=".txt,.srt"
              onChange={handleFileUpload}
              className="hidden"
            />
          </label>
          <span className="text-xs text-muted-foreground">or paste below</span>
        </div>
        <textarea
          value={rawText}
          onChange={(e) => setRawText(e.target.value)}
          placeholder="Paste your Otter.ai transcript text here…"
          rows={10}
          className="w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-ring"
        />
        <button
          type="button"
          onClick={handleParse}
          disabled={!rawText.trim()}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          Parse Transcript
        </button>
      </div>

      {/* ─── Preview ─── */}
      {parseResult && (
        <div className="space-y-2">
          <h2 className="text-sm font-semibold">2. Preview Parsed Segments</h2>
          <SegmentPreview
            segments={segments}
            speakerStats={parseResult.calculated.speakerStats}
            speakers={parseResult.calculated.speakersDetected}
            suggestedPrimary={parseResult.calculated.suggestedPrimarySpeaker}
            totalSeconds={parseResult.calculated.totalSeconds}
          />
        </div>
      )}

      {/* ─── Metadata form ─── */}
      <div className="rounded-lg border border-border bg-card p-4 space-y-4">
        <h2 className="text-sm font-semibold">
          {parseResult ? "3." : "2."} Transcript Metadata
        </h2>

        <div className="grid gap-4 sm:grid-cols-2">
          {/* Title */}
          <div className="sm:col-span-2">
            <label className="mb-1 block text-sm font-medium">Title *</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Mayor Mamdani Holds Press Conference…"
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>

          {/* Event date */}
          <div>
            <label className="mb-1 block text-sm font-medium">
              Event Date *
            </label>
            <input
              type="date"
              value={eventDate}
              onChange={(e) => setEventDate(e.target.value)}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>

          {/* Speech type */}
          <div>
            <label className="mb-1 block text-sm font-medium">
              Speech Type *
            </label>
            <select
              value={speechType}
              onChange={(e) => setSpeechType(e.target.value)}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            >
              <option value="">Select…</option>
              {SPEECH_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            {speechType === "Other" && (
              <input
                type="text"
                value={customSpeechType}
                onChange={(e) => setCustomSpeechType(e.target.value)}
                placeholder="Custom speech type"
                className="mt-2 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
            )}
          </div>

          {/* Primary speaker */}
          <div>
            <label className="mb-1 block text-sm font-medium">
              Primary Speaker *
            </label>
            <input
              type="text"
              value={primarySpeaker}
              onChange={(e) => setPrimarySpeaker(e.target.value)}
              placeholder="e.g. Zohran Mamdani"
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>

          {/* Total length */}
          <div>
            <label className="mb-1 block text-sm font-medium">
              Total Length (seconds)
            </label>
            <input
              type="number"
              value={totalLength}
              onChange={(e) =>
                setTotalLength(e.target.value ? Number(e.target.value) : "")
              }
              placeholder="Auto-calculated if blank"
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>

          {/* Speakers present */}
          <div className="sm:col-span-2">
            <TagInput
              label="Speakers Present"
              value={speakersPresent}
              onChange={setSpeakersPresent}
              placeholder="Type speaker name and press Enter…"
            />
          </div>

          {/* Key themes */}
          <div className="sm:col-span-2">
            <TagInput
              label="Key Themes"
              value={keyThemes}
              onChange={setKeyThemes}
              placeholder="Type theme and press Enter…"
            />
          </div>

          {/* Has Q&A */}
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="has-qa"
              checked={hasQAndA}
              onChange={(e) => setHasQAndA(e.target.checked)}
              className="rounded border-input"
            />
            <label htmlFor="has-qa" className="text-sm">
              Has Q&A section
            </label>
          </div>
        </div>
      </div>

      {/* ─── Actions ─── */}
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={handleSave}
          disabled={saving}
          className="rounded-md bg-primary px-6 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          {saving ? "Saving…" : isEdit ? "Update Transcript" : "Save Transcript"}
        </button>

        <button
          type="button"
          onClick={() => router.push("/admin/transcripts")}
          className="rounded-md border border-input px-4 py-2 text-sm hover:bg-accent"
        >
          Cancel
        </button>

        {isEdit && (
          <button
            type="button"
            onClick={handleDelete}
            disabled={deleting}
            className="ml-auto rounded-md bg-destructive px-4 py-2 text-sm font-medium text-destructive-foreground hover:bg-destructive/90 disabled:opacity-50"
          >
            {deleting ? "Deleting…" : "Delete"}
          </button>
        )}
      </div>
    </div>
  );
}

