"use client";

import type { ParsedSegment, SpeakerStats } from "@/lib/parsers/otter";
import { secondsToTime } from "@/lib/parsers/otter";

// Assign each speaker a distinct color from a palette
const SPEAKER_COLORS = [
  "text-blue-400",
  "text-emerald-400",
  "text-amber-400",
  "text-purple-400",
  "text-rose-400",
  "text-cyan-400",
  "text-orange-400",
  "text-pink-400",
];

function speakerColor(speakers: string[], name: string): string {
  const idx = speakers.indexOf(name);
  return SPEAKER_COLORS[idx % SPEAKER_COLORS.length];
}

interface SegmentPreviewProps {
  segments: ParsedSegment[];
  speakerStats: Record<string, SpeakerStats>;
  speakers: string[];
  suggestedPrimary: string | null;
  totalSeconds: number | null;
}

export function SegmentPreview({
  segments,
  speakerStats,
  speakers,
  suggestedPrimary,
  totalSeconds,
}: SegmentPreviewProps) {
  if (segments.length === 0) return null;

  return (
    <div className="space-y-4">
      {/* Stats banner */}
      <div className="grid grid-cols-2 gap-3 rounded-lg border border-border bg-card p-4 sm:grid-cols-4">
        <div>
          <div className="text-xs text-muted-foreground">Segments</div>
          <div className="text-lg font-semibold">{segments.length}</div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Total Duration</div>
          <div className="text-lg font-semibold">
            {totalSeconds ? secondsToTime(totalSeconds) : "—"}
          </div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Speakers</div>
          <div className="text-lg font-semibold">{speakers.length}</div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Suggested Primary</div>
          <div className="text-lg font-semibold truncate">
            {suggestedPrimary || "—"}
          </div>
        </div>
      </div>

      {/* Speaker breakdown */}
      <div className="rounded-lg border border-border bg-card p-4">
        <h3 className="mb-2 text-sm font-semibold">Speaker Breakdown</h3>
        <div className="space-y-1.5">
          {speakers.map((sp) => {
            const st = speakerStats[sp];
            const pct =
              totalSeconds && st.totalSeconds
                ? Math.round((st.totalSeconds / totalSeconds) * 100)
                : null;
            return (
              <div key={sp} className="flex items-center gap-3 text-sm">
                <span
                  className={`w-40 truncate font-medium ${speakerColor(speakers, sp)}`}
                >
                  {sp}
                </span>
                <span className="text-muted-foreground">
                  {st.turnCount} turn{st.turnCount !== 1 ? "s" : ""}
                </span>
                <span className="text-muted-foreground">
                  {st.wordCount} words
                </span>
                {st.totalSeconds > 0 && (
                  <span className="text-muted-foreground">
                    {secondsToTime(st.totalSeconds)}
                    {pct !== null && ` (${pct}%)`}
                  </span>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Segment list */}
      <div className="rounded-lg border border-border bg-card">
        <h3 className="border-b border-border px-4 py-2 text-sm font-semibold">
          Parsed Segments
        </h3>
        <div className="max-h-[500px] overflow-y-auto divide-y divide-border">
          {segments.map((seg, i) => (
            <div key={i} className="px-4 py-2.5 text-sm">
              <div className="mb-1 flex items-center gap-2">
                <span
                  className={`font-semibold ${speakerColor(speakers, seg.speaker)}`}
                >
                  {seg.speaker}
                </span>
                <span className="text-xs text-muted-foreground">
                  {secondsToTime(seg.start_seconds)}
                  {seg.end_seconds !== null &&
                    ` → ${secondsToTime(seg.end_seconds)}`}
                </span>
              </div>
              <p className="text-foreground/80 leading-relaxed">{seg.text}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

