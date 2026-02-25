"use client";

import { useState, useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  parseOtterTranscript,
  computeQAAnalyticsFromPairs,
  type ParseResult,
  type ParsedSegment,
  type QAPair,
} from "@/lib/parsers/otter";
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
    /** Previously saved curated Q&A pairs */
    qa_data?: QAPair[] | null;
    /** Previously saved auto-detected Q&A pairs (before user edits) */
    qa_data_auto?: QAPair[] | null;
    /** Keys of pairs the user has removed */
    qa_overrides?: { removedKeys: string[] } | null;
  };
}

export function TranscriptForm({ initialData }: TranscriptFormProps) {
  const router = useRouter();
  const isEdit = !!initialData;

  // Available speakers (for quick re-use)
  const [availableSpeakers, setAvailableSpeakers] = useState<string[]>([]);

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

  // Q&A curation state
  // autoPairs  — latest auto-detected pairs (from last parse, or loaded from db)
  // removedKeys — set of qaKeys the user has manually removed
  const [autoPairs, setAutoPairs] = useState<QAPair[]>(
    initialData?.qa_data_auto ?? initialData?.qa_data ?? []
  );
  const [removedKeys, setRemovedKeys] = useState<Set<string>>(
    new Set(initialData?.qa_overrides?.removedKeys ?? [])
  );
  const [showRemoved, setShowRemoved] = useState(false);

  // Curated pairs = auto pairs minus removed keys
  const curatedPairs = autoPairs.filter((p) => !removedKeys.has(p.qaKey));
  const removedPairs = autoPairs.filter((p) => removedKeys.has(p.qaKey));
  const curatedAnalytics =
    curatedPairs.length > 0 || autoPairs.length > 0
      ? computeQAAnalyticsFromPairs(curatedPairs)
      : null;

  // UI state
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    fetch("/api/search/filters", { cache: "no-store" })
      .then((r) => r.json())
      .then((data) => {
        if (Array.isArray(data?.speakers)) setAvailableSpeakers(data.speakers);
      })
      .catch(() => {});
  }, []);

  // Parse the raw text
  const handleParse = useCallback(() => {
    if (!rawText.trim()) return;
    const result = parseOtterTranscript(rawText, { detectQA: hasQAndA });
    setParseResult(result);
    setSegments(result.segments);

    if (result.qaAnalytics) {
      // Replace auto pairs with freshly detected ones; keep existing overrides in place
      setAutoPairs(result.qaAnalytics.pairs);
    }

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
  }, [rawText, hasQAndA, primarySpeaker, speakersPresent.length, totalLength]);

  // Remove a Q&A pair (send feedback event if editing an existing transcript)
  async function handleRemoveQA(pair: QAPair) {
    setRemovedKeys((prev) => new Set([...prev, pair.qaKey]));
    if (initialData?.id) {
      await fetch("/api/admin/qa-feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          transcriptId: initialData.id,
          qaKey: pair.qaKey,
          action: "removed",
          pairSnapshot: pair,
        }),
      }).catch(() => {});
    }
  }

  // Restore a previously removed Q&A pair
  async function handleRestoreQA(pair: QAPair) {
    setRemovedKeys((prev) => {
      const next = new Set(prev);
      next.delete(pair.qaKey);
      return next;
    });
    if (initialData?.id) {
      await fetch("/api/admin/qa-feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          transcriptId: initialData.id,
          qaKey: pair.qaKey,
          action: "restored",
          pairSnapshot: pair,
        }),
      }).catch(() => {});
    }
  }

  // Reset all removals and go back to fully auto-detected list
  function handleResetQA() {
    setRemovedKeys(new Set());
  }

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
      // Q&A analytics — save curated pairs + raw auto pairs + overrides
      question_count: curatedAnalytics?.questionCount ?? null,
      avg_response_length_words: curatedAnalytics?.avgResponseWords ?? null,
      avg_response_length_seconds: curatedAnalytics?.avgResponseSeconds ?? null,
      qa_data: curatedPairs.length > 0 ? curatedPairs : null,
      qa_data_auto: autoPairs.length > 0 ? autoPairs : null,
      qa_overrides: removedKeys.size > 0 ? { removedKeys: [...removedKeys] } : null,
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
              list="available-speakers"
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
            <datalist id="available-speakers">
              {availableSpeakers.map((s) => (
                <option key={s} value={s} />
              ))}
            </datalist>
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
          <div className="sm:col-span-2">
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
            
            {/* Q&A Analytics Display */}
            {hasQAndA && autoPairs.length > 0 && (
              <div className="mt-4 rounded-md border border-blue-200 bg-blue-50 p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-blue-900">
                    Q&amp;A Detected
                  </h3>
                  <div className="flex items-center gap-2">
                    {removedKeys.size > 0 && (
                      <button
                        type="button"
                        onClick={handleResetQA}
                        className="text-xs text-blue-600 hover:text-blue-800 underline"
                      >
                        Reset all removals ({removedKeys.size})
                      </button>
                    )}
                    {removedPairs.length > 0 && (
                      <button
                        type="button"
                        onClick={() => setShowRemoved((v) => !v)}
                        className="text-xs text-gray-500 hover:text-gray-700 underline"
                      >
                        {showRemoved ? "Hide removed" : `Show removed (${removedPairs.length})`}
                      </button>
                    )}
                  </div>
                </div>

                <div className="grid gap-3 sm:grid-cols-3 text-sm">
                  <div>
                    <div className="text-blue-600 font-medium">Questions</div>
                    <div className="text-2xl font-bold text-blue-900">
                      {curatedAnalytics?.questionCount ?? 0}
                      {removedKeys.size > 0 && (
                        <span className="ml-1 text-sm font-normal text-gray-400">
                          / {autoPairs.length} detected
                        </span>
                      )}
                    </div>
                  </div>
                  <div>
                    <div className="text-blue-600 font-medium">Avg Response Length</div>
                    <div className="text-2xl font-bold text-blue-900">
                      {curatedAnalytics?.avgResponseWords ?? 0} words
                    </div>
                  </div>
                  <div>
                    <div className="text-blue-600 font-medium">Avg Response Time</div>
                    <div className="text-2xl font-bold text-blue-900">
                      {curatedAnalytics?.avgResponseSeconds != null
                        ? `${curatedAnalytics.avgResponseSeconds}s`
                        : "N/A"}
                    </div>
                  </div>
                </div>

                {/* Active Q&A pairs */}
                <div className="space-y-2 max-h-96 overflow-y-auto">
                  {curatedPairs.length === 0 && (
                    <p className="text-xs text-gray-500 italic">
                      All detected questions have been removed.
                    </p>
                  )}
                  {curatedPairs.map((pair, idx) => (
                    <div
                      key={pair.qaKey}
                      className="rounded border border-blue-200 bg-white p-3 text-xs flex gap-2"
                    >
                      <div className="flex-1 min-w-0">
                        <div className="font-medium text-blue-900">
                          Q{idx + 1}: {pair.questionSpeaker}
                        </div>
                        <div className="mt-1 text-gray-700 italic truncate">
                          &ldquo;{pair.questionText}&rdquo;
                        </div>
                        <div className="mt-1 text-gray-500">
                          Response: {pair.responseWordCount} words
                          {pair.responseDurationSeconds != null &&
                            ` • ${pair.responseDurationSeconds.toFixed(1)}s`}
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => handleRemoveQA(pair)}
                        title="Remove this Q&A pair"
                        className="shrink-0 self-start rounded px-2 py-1 text-xs font-medium text-red-600 hover:bg-red-50 border border-red-200"
                      >
                        Remove
                      </button>
                    </div>
                  ))}
                </div>

                {/* Removed Q&A pairs (shown when toggled) */}
                {showRemoved && removedPairs.length > 0 && (
                  <div className="mt-2 space-y-2 max-h-64 overflow-y-auto border-t border-blue-100 pt-2">
                    <div className="text-xs font-medium text-gray-400 uppercase tracking-wide">
                      Removed — will not be saved
                    </div>
                    {removedPairs.map((pair) => (
                      <div
                        key={pair.qaKey}
                        className="rounded border border-gray-200 bg-gray-50 p-3 text-xs flex gap-2 opacity-60"
                      >
                        <div className="flex-1 min-w-0">
                          <div className="font-medium text-gray-600">
                            {pair.questionSpeaker}
                          </div>
                          <div className="mt-1 text-gray-500 italic truncate">
                            &ldquo;{pair.questionText}&rdquo;
                          </div>
                        </div>
                        <button
                          type="button"
                          onClick={() => handleRestoreQA(pair)}
                          title="Restore this Q&A pair"
                          className="shrink-0 self-start rounded px-2 py-1 text-xs font-medium text-green-700 hover:bg-green-50 border border-green-200"
                        >
                          Restore
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {hasQAndA && autoPairs.length === 0 && parseResult && (
              <div className="mt-4 rounded-md border border-yellow-200 bg-yellow-50 p-3 text-sm text-yellow-800">
                No questions detected. Detection requires a clear question (ending in ? or starting with an interrogative) followed by a substantive answer from the primary speaker.
              </div>
            )}

            {hasQAndA && autoPairs.length === 0 && !parseResult && (
              <div className="mt-4 rounded-md border border-gray-200 bg-gray-50 p-3 text-sm text-gray-600">
                Click &ldquo;Parse Transcript&rdquo; to auto-detect Q&amp;A pairs
              </div>
            )}
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

