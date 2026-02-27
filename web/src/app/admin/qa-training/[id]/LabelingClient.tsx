"use client";

import { useState, useCallback } from "react";
import Link from "next/link";
import type { CandidateExchange } from "@/lib/parsers/otter";

interface ExistingLabel {
  id: string;
  questionText: string;
  isQA: boolean;
  reasoning: string | null;
}

interface LabelingClientProps {
  transcriptId: string;
  transcriptTitle: string;
  primarySpeaker: string;
  candidates: CandidateExchange[];
  existingLabels: ExistingLabel[];
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

function truncate(text: string, words: number): string {
  const parts = text.split(/\s+/);
  if (parts.length <= words) return text;
  return parts.slice(0, words).join(" ") + "…";
}

export function LabelingClient({
  transcriptId,
  transcriptTitle,
  primarySpeaker,
  candidates,
  existingLabels,
}: LabelingClientProps) {
  // Build initial label map from existing labels
  const initLabels = (): Record<string, { isQA: boolean; reasoning: string }> => {
    const map: Record<string, { isQA: boolean; reasoning: string }> = {};
    for (const l of existingLabels) {
      map[l.questionText] = { isQA: l.isQA, reasoning: l.reasoning ?? "" };
    }
    return map;
  };

  const [labels, setLabels] = useState(initLabels);
  const [currentIdx, setCurrentIdx] = useState(() => {
    // Start at first unlabeled card
    const first = candidates.findIndex((c) => !(c.questionText in initLabels()));
    return first >= 0 ? first : 0;
  });
  const [reasoning, setReasoning] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [showFullResponse, setShowFullResponse] = useState(false);
  const [viewMode, setViewMode] = useState<"card" | "overview">("card");

  const current = candidates[currentIdx];
  const labeledCount = Object.keys(labels).length;
  const totalCount = candidates.length;
  const allDone = labeledCount >= totalCount;

  // Pre-fill reasoning when switching cards
  const goTo = useCallback(
    (idx: number) => {
      const cand = candidates[idx];
      if (!cand) return;
      const existing = labels[cand.questionText];
      setReasoning(existing?.reasoning ?? "");
      setShowFullResponse(false);
      setCurrentIdx(idx);
    },
    [candidates, labels]
  );

  const handleLabel = useCallback(
    async (isQA: boolean) => {
      if (!current) return;
      setSaving(true);
      setSaveError("");

      try {
        const res = await fetch("/api/admin/qa-labels", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            transcriptId,
            questionSpeaker: current.questionSpeaker,
            questionText: current.questionText,
            responseSpeaker: current.responseSpeaker,
            responseText: current.responseText,
            isQA,
            reasoning: reasoning.trim() || null,
          }),
        });

        if (!res.ok) {
          setSaveError("Failed to save label");
          return;
        }

        setLabels((prev) => ({
          ...prev,
          [current.questionText]: { isQA, reasoning: reasoning.trim() },
        }));

        // Advance to next unlabeled card
        const nextUnlabeled = candidates.findIndex(
          (c, i) =>
            i > currentIdx &&
            !(c.questionText in labels) &&
            c.questionText !== current.questionText
        );
        if (nextUnlabeled >= 0) {
          goTo(nextUnlabeled);
        } else {
          // Wrap around or stay at end
          const nextAny = candidates.findIndex(
            (c, i) =>
              i !== currentIdx &&
              !(c.questionText in { ...labels, [current.questionText]: true })
          );
          if (nextAny >= 0) {
            goTo(nextAny);
          } else {
            setReasoning("");
          }
        }
      } catch {
        setSaveError("Network error");
      } finally {
        setSaving(false);
      }
    },
    [current, transcriptId, reasoning, labels, currentIdx, candidates, goTo]
  );

  if (candidates.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-border p-8 text-center text-muted-foreground">
        <p>No candidate exchanges found in this transcript.</p>
        <p className="mt-2 text-sm">
          This transcript may not have enough non-primary-speaker segments with ≥10 words.
        </p>
        <Link href="/admin/qa-training" className="mt-4 inline-block text-primary underline text-sm">
          Back to training
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <Link href="/admin/qa-training" className="text-sm text-muted-foreground hover:text-foreground">
            ← Back to training
          </Link>
          <h1 className="mt-1 text-xl font-bold">{transcriptTitle}</h1>
          <p className="text-sm text-muted-foreground">
            Primary speaker: <span className="font-medium">{primarySpeaker}</span>
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={() => setViewMode(viewMode === "card" ? "overview" : "card")}
            className="rounded-md border border-input px-3 py-1.5 text-xs hover:bg-accent"
          >
            {viewMode === "card" ? "Overview" : "Flashcard"}
          </button>
        </div>
      </div>

      {/* Progress bar */}
      <div className="space-y-1">
        <div className="flex justify-between text-xs text-muted-foreground">
          <span>{labeledCount} labeled</span>
          <span>{totalCount} candidates</span>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
          <div
            className="h-full rounded-full bg-primary transition-all"
            style={{ width: `${totalCount > 0 ? (labeledCount / totalCount) * 100 : 0}%` }}
          />
        </div>
      </div>

      {allDone && (
        <div className="rounded-md border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">
          All {totalCount} candidates labeled for this transcript. You can still click any card below to update a label.
        </div>
      )}

      {saveError && (
        <div className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {saveError}
        </div>
      )}

      {/* ── OVERVIEW MODE ── */}
      {viewMode === "overview" && (
        <div className="space-y-2">
          {candidates.map((c, idx) => {
            const lbl = labels[c.questionText];
            return (
              <button
                key={c.qaKey}
                type="button"
                onClick={() => { setViewMode("card"); goTo(idx); }}
                className={`w-full text-left rounded-lg border p-3 text-sm hover:bg-accent transition-colors ${
                  currentIdx === idx ? "border-primary ring-1 ring-primary" : "border-border"
                }`}
              >
                <div className="flex items-start gap-3">
                  <div className="shrink-0 mt-0.5">
                    {lbl === undefined ? (
                      <span className="inline-block h-5 w-5 rounded-full border-2 border-muted-foreground/30" />
                    ) : lbl.isQA ? (
                      <span className="inline-block rounded bg-green-100 px-1.5 py-0.5 text-xs font-bold text-green-700">Y</span>
                    ) : (
                      <span className="inline-block rounded bg-red-100 px-1.5 py-0.5 text-xs font-bold text-red-600">N</span>
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-xs text-muted-foreground">
                        {c.questionSpeaker} • {formatTime(c.questionStart)}
                      </span>
                    </div>
                    <p className="mt-0.5 line-clamp-2 text-xs text-foreground">
                      {c.questionText}
                    </p>
                    {lbl?.reasoning && (
                      <p className="mt-0.5 text-xs text-muted-foreground italic">
                        Reason: {lbl.reasoning}
                      </p>
                    )}
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      )}

      {/* ── FLASHCARD MODE ── */}
      {viewMode === "card" && current && (
        <div className="space-y-4">
          {/* Navigation dots */}
          <div className="flex items-center gap-1 flex-wrap">
            {candidates.map((c, idx) => {
              const lbl = labels[c.questionText];
              return (
                <button
                  key={c.qaKey}
                  type="button"
                  onClick={() => goTo(idx)}
                  title={`Card ${idx + 1}${lbl ? (lbl.isQA ? " — Yes" : " — No") : " — unlabeled"}`}
                  className={`h-2.5 w-2.5 rounded-full transition-all ${
                    idx === currentIdx
                      ? "ring-2 ring-primary ring-offset-1"
                      : ""
                  } ${
                    lbl === undefined
                      ? "bg-muted-foreground/30"
                      : lbl.isQA
                      ? "bg-green-500"
                      : "bg-red-400"
                  }`}
                />
              );
            })}
          </div>

          {/* Main card */}
          <div className="rounded-xl border border-border bg-card shadow-sm overflow-hidden">
            {/* Card header */}
            <div className="border-b border-border bg-muted/30 px-5 py-3 flex items-center justify-between">
              <div>
                <span className="font-semibold text-sm">{current.questionSpeaker}</span>
                <span className="ml-2 text-xs text-muted-foreground">
                  {formatTime(current.questionStart)}
                </span>
                {labels[current.questionText] !== undefined && (
                  <span
                    className={`ml-3 rounded px-2 py-0.5 text-xs font-bold ${
                      labels[current.questionText].isQA
                        ? "bg-green-100 text-green-700"
                        : "bg-red-100 text-red-600"
                    }`}
                  >
                    {labels[current.questionText].isQA ? "Labeled: Q&A" : "Labeled: Not Q&A"}
                  </span>
                )}
              </div>
              <span className="text-xs text-muted-foreground tabular-nums">
                {currentIdx + 1} / {totalCount}
              </span>
            </div>

            {/* Question */}
            <div className="px-5 pt-4 pb-3">
              <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1.5">
                Question / Statement
              </div>
              <p className="text-sm leading-relaxed text-foreground">
                &ldquo;{current.questionText}&rdquo;
              </p>
            </div>

            {/* Divider */}
            <div className="mx-5 border-t border-dashed border-border" />

            {/* Response */}
            <div className="px-5 pt-3 pb-4">
              <div className="flex items-center justify-between mb-1.5">
                <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  {current.responseSpeaker} responds
                  <span className="ml-1 font-normal text-muted-foreground/70">
                    ({current.responseWordCount} words)
                  </span>
                </div>
                {current.responseWordCount > 60 && (
                  <button
                    type="button"
                    onClick={() => setShowFullResponse((v) => !v)}
                    className="text-xs text-primary hover:underline"
                  >
                    {showFullResponse ? "Show less" : "Show full response"}
                  </button>
                )}
              </div>
              <p className="text-sm leading-relaxed text-muted-foreground">
                &ldquo;
                {showFullResponse
                  ? current.responseText
                  : truncate(current.responseText, 60)}
                &rdquo;
              </p>
            </div>

            {/* Reasoning */}
            <div className="border-t border-border px-5 py-3">
              <label className="block text-xs font-medium text-muted-foreground mb-1">
                Reasoning <span className="font-normal">(optional — helps train the AI)</span>
              </label>
              <textarea
                value={reasoning}
                onChange={(e) => setReasoning(e.target.value)}
                placeholder="e.g. Reporter is directly asking for the mayor's position on X — or — This is just the moderator redirecting, not a real Q&amp;A"
                rows={2}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring resize-none"
              />
            </div>

            {/* Action buttons */}
            <div className="border-t border-border bg-muted/20 px-5 py-3 flex items-center gap-3">
              <button
                type="button"
                onClick={() => handleLabel(true)}
                disabled={saving}
                className="flex-1 rounded-lg bg-green-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-green-700 disabled:opacity-50 transition-colors"
              >
                Yes, this is Q&A
              </button>
              <button
                type="button"
                onClick={() => handleLabel(false)}
                disabled={saving}
                className="flex-1 rounded-lg bg-red-500 px-4 py-2.5 text-sm font-semibold text-white hover:bg-red-600 disabled:opacity-50 transition-colors"
              >
                Not Q&A
              </button>
            </div>
          </div>

          {/* Prev / Next */}
          <div className="flex items-center justify-between">
            <button
              type="button"
              onClick={() => goTo(Math.max(0, currentIdx - 1))}
              disabled={currentIdx === 0}
              className="rounded-md border border-input px-3 py-1.5 text-xs hover:bg-accent disabled:opacity-40"
            >
              ← Previous
            </button>
            <button
              type="button"
              onClick={() => goTo(Math.min(totalCount - 1, currentIdx + 1))}
              disabled={currentIdx === totalCount - 1}
              className="rounded-md border border-input px-3 py-1.5 text-xs hover:bg-accent disabled:opacity-40"
            >
              Next →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
