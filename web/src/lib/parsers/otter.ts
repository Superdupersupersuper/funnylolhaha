/**
 * Otter.ai transcript parser
 *
 * Supports two export formats:
 *  1. TXT  – lines like "Speaker Name  M:SS  \ntext..." (Otter default)
 *           – or "[HH:MM:SS] Speaker: text"
 *           – or "[MM:SS] Speaker: text"
 *  2. SRT  – standard subtitle cues with optional "Speaker:" prefix
 *
 * Returns structured segments + derived analytics.
 */

// ─── Types ──────────────────────────────────────────────────────────────────

export interface ParsedSegment {
  speaker: string;
  start_seconds: number;
  end_seconds: number | null;
  text: string;
}

export interface SpeakerStats {
  totalSeconds: number;
  turnCount: number;
  wordCount: number;
  avgTurnSeconds: number;
}

export interface ParseResult {
  segments: ParsedSegment[];
  calculated: {
    totalSeconds: number | null;
    speakerStats: Record<string, SpeakerStats>;
    suggestedPrimarySpeaker: string | null;
    speakersDetected: string[];
    segmentCount: number;
  };
}

// ─── Helpers ────────────────────────────────────────────────────────────────

/** Convert a time string to total seconds. Handles H:MM:SS, MM:SS, M:SS, and SRT comma format. */
export function timeToSeconds(ts: string): number {
  // SRT uses comma for millis: "00:01:23,456"
  const cleaned = ts.replace(",", ".");
  const parts = cleaned.split(":").map(Number);
  if (parts.length === 3) {
    return parts[0] * 3600 + parts[1] * 60 + parts[2];
  }
  if (parts.length === 2) {
    return parts[0] * 60 + parts[1];
  }
  return parts[0] || 0;
}

/** Best-effort format seconds as M:SS or H:MM:SS. */
export function secondsToTime(s: number): string {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
  return `${m}:${String(sec).padStart(2, "0")}`;
}

// ─── Detect format ──────────────────────────────────────────────────────────

type Format = "otter-txt" | "bracketed-txt" | "srt" | "plain";

function detectFormat(raw: string): Format {
  const lines = raw.split("\n").slice(0, 30);

  // SRT: look for "-->", very distinctive
  if (lines.some((l) => l.includes("-->"))) return "srt";

  // Otter default TXT: "Speaker Name  M:SS  " header lines
  // Pattern: non-empty text, then 2+ spaces, then digits:digits, then 2+ spaces
  const otterHeaderRe = /^.+\s{2,}\d{1,2}:\d{2}(?::\d{2})?\s*$/;
  if (lines.some((l) => otterHeaderRe.test(l))) return "otter-txt";

  // Bracketed: [00:02:10] Speaker: text  OR  [MM:SS] Speaker: text
  const bracketRe = /^\[?\d{1,2}:\d{2}(?::\d{2})?\]?\s*[-–]?\s*\w/;
  if (lines.some((l) => bracketRe.test(l))) return "bracketed-txt";

  return "plain";
}

// ─── Otter TXT parser ──────────────────────────────────────────────────────
//
// Format observed in the real Mamdani file:
//   Speaker Name  M:SS  \n
//   text content that may span multiple lines\n
//   \n
//   Speaker Name  M:SS  \n
//   more text...\n

function parseOtterTxt(raw: string): ParsedSegment[] {
  const lines = raw.split("\n");
  const segments: ParsedSegment[] = [];

  // Header line regex: captures speaker name (trimmed) + timestamp
  // "Zohran Mamdani  0:22  " or "Speaker 1  5:38  "
  const headerRe = /^(.+?)\s{2,}(\d{1,2}:\d{2}(?::\d{2})?)\s*$/;

  let currentSpeaker: string | null = null;
  let currentStart: number | null = null;
  let textLines: string[] = [];

  function flush() {
    if (currentSpeaker !== null && currentStart !== null && textLines.length > 0) {
      const text = textLines
        .join(" ")
        .replace(/\s+/g, " ")
        .trim();
      if (text && !text.startsWith("Transcribed by")) {
        segments.push({
          speaker: currentSpeaker,
          start_seconds: currentStart,
          end_seconds: null, // will be inferred later
          text,
        });
      }
    }
    textLines = [];
  }

  for (const line of lines) {
    const trimmed = line.trim();

    // Skip the Otter footer
    if (trimmed.startsWith("Transcribed by")) continue;

    const match = headerRe.exec(line);
    if (match) {
      flush();
      currentSpeaker = match[1].trim();
      currentStart = timeToSeconds(match[2]);
    } else if (trimmed.length > 0) {
      textLines.push(trimmed);
    }
    // blank lines are just separators — ignore
  }

  flush();
  return segments;
}

// ─── Bracketed TXT parser ──────────────────────────────────────────────────
//
// Formats:
//   [00:02:10] Speaker: text...
//   [MM:SS] - Speaker: text...

function parseBracketedTxt(raw: string): ParsedSegment[] {
  const lines = raw.split("\n");
  const segments: ParsedSegment[] = [];

  // Regex: optional bracket, timestamp, optional bracket, optional dash, speaker, colon, text
  const lineRe =
    /^\[?(\d{1,2}:\d{2}(?::\d{2})?)\]?\s*[-–]?\s*([^:]+?):\s*(.+)$/;

  let current: { speaker: string; start: number; textParts: string[] } | null = null;

  function flush() {
    if (current && current.textParts.length > 0) {
      segments.push({
        speaker: current.speaker.trim(),
        start_seconds: current.start,
        end_seconds: null,
        text: current.textParts.join(" ").replace(/\s+/g, " ").trim(),
      });
    }
    current = null;
  }

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("Transcribed by")) continue;

    const m = lineRe.exec(trimmed);
    if (m) {
      flush();
      current = {
        speaker: m[2],
        start: timeToSeconds(m[1]),
        textParts: [m[3]],
      };
    } else if (current) {
      // continuation line
      current.textParts.push(trimmed);
    }
  }
  flush();
  return segments;
}

// ─── SRT parser ─────────────────────────────────────────────────────────────
//
// 1
// 00:00:10,500 --> 00:00:15,000
// Speaker: text goes here
//
// 2
// 00:00:15,500 --> 00:00:20,000
// More text (no speaker prefix = same or unknown)

function parseSrt(raw: string): ParsedSegment[] {
  const blocks = raw
    .replace(/\r\n/g, "\n")
    .split(/\n\n+/)
    .filter((b) => b.trim().length > 0);

  const segments: ParsedSegment[] = [];
  const timeRe = /(\d{2}:\d{2}:\d{2}[.,]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[.,]\d{3})/;
  const speakerRe = /^([^:]{1,40}):\s*(.+)$/;

  for (const block of blocks) {
    const lines = block.split("\n").map((l) => l.trim());
    // Find the time line
    const timeLine = lines.find((l) => timeRe.test(l));
    if (!timeLine) continue;

    const tm = timeRe.exec(timeLine)!;
    const startSec = timeToSeconds(tm[1]);
    const endSec = timeToSeconds(tm[2]);

    // Text lines come after the time line
    const timeIdx = lines.indexOf(timeLine);
    const textLines = lines.slice(timeIdx + 1).filter((l) => l.length > 0);
    if (textLines.length === 0) continue;

    // Check if first text line has a "Speaker:" prefix
    const spMatch = speakerRe.exec(textLines[0]);
    let speaker = "Unknown";
    let textParts: string[];

    if (spMatch) {
      speaker = spMatch[1].trim();
      textParts = [spMatch[2], ...textLines.slice(1)];
    } else {
      textParts = textLines;
    }

    segments.push({
      speaker,
      start_seconds: startSec,
      end_seconds: endSec,
      text: textParts.join(" ").replace(/\s+/g, " ").trim(),
    });
  }

  return segments;
}

// ─── Plain-text fallback ────────────────────────────────────────────────────

function parsePlain(raw: string): ParsedSegment[] {
  const text = raw.replace(/\r\n/g, "\n").trim();
  if (!text) return [];

  // Try splitting by double newlines into paragraphs
  const paragraphs = text.split(/\n\n+/).filter((p) => p.trim().length > 0);

  return paragraphs.map((p, i) => ({
    speaker: "Unknown",
    start_seconds: 0,
    end_seconds: null,
    text: p.replace(/\s+/g, " ").trim(),
  }));
}

// ─── Post-processing ────────────────────────────────────────────────────────

/** Infer end_seconds from next segment's start_seconds for formats that lack end times. */
function inferEndTimes(segments: ParsedSegment[]): ParsedSegment[] {
  return segments.map((seg, i) => {
    if (seg.end_seconds !== null) return seg;
    const next = segments[i + 1];
    return {
      ...seg,
      end_seconds: next ? next.start_seconds : null,
    };
  });
}

/** Merge consecutive segments by same speaker when gap <= mergeGapSec. */
function smartMerge(
  segments: ParsedSegment[],
  mergeGapSec = 3
): ParsedSegment[] {
  if (segments.length === 0) return [];

  const merged: ParsedSegment[] = [{ ...segments[0] }];

  for (let i = 1; i < segments.length; i++) {
    const prev = merged[merged.length - 1];
    const cur = segments[i];

    const sameSpeaker = prev.speaker === cur.speaker;
    const gap =
      prev.end_seconds !== null
        ? cur.start_seconds - prev.end_seconds
        : cur.start_seconds - prev.start_seconds;

    if (sameSpeaker && gap <= mergeGapSec && gap >= 0) {
      // merge
      prev.text = prev.text + " " + cur.text;
      prev.end_seconds = cur.end_seconds ?? prev.end_seconds;
    } else {
      merged.push({ ...cur });
    }
  }

  return merged;
}

/** Build speaker stats from parsed segments. */
function buildStats(segments: ParsedSegment[]) {
  const stats: Record<string, SpeakerStats> = {};

  for (const seg of segments) {
    if (!stats[seg.speaker]) {
      stats[seg.speaker] = {
        totalSeconds: 0,
        turnCount: 0,
        wordCount: 0,
        avgTurnSeconds: 0,
      };
    }
    const s = stats[seg.speaker];
    s.turnCount += 1;
    s.wordCount += seg.text.split(/\s+/).length;
    if (seg.end_seconds !== null) {
      s.totalSeconds += seg.end_seconds - seg.start_seconds;
    }
  }

  // calculate avg
  for (const s of Object.values(stats)) {
    s.avgTurnSeconds = s.turnCount > 0 ? s.totalSeconds / s.turnCount : 0;
    // Round for display
    s.totalSeconds = Math.round(s.totalSeconds * 10) / 10;
    s.avgTurnSeconds = Math.round(s.avgTurnSeconds * 10) / 10;
  }

  return stats;
}

// ─── Main entry ─────────────────────────────────────────────────────────────

export interface ParseOptions {
  /** Merge consecutive same-speaker segments when gap <= this many seconds. Set 0 to disable. */
  mergeGapSeconds?: number;
}

export function parseOtterTranscript(
  rawText: string,
  options: ParseOptions = {}
): ParseResult {
  const { mergeGapSeconds = 3 } = options;

  const format = detectFormat(rawText);

  let segments: ParsedSegment[];
  switch (format) {
    case "otter-txt":
      segments = parseOtterTxt(rawText);
      break;
    case "bracketed-txt":
      segments = parseBracketedTxt(rawText);
      break;
    case "srt":
      segments = parseSrt(rawText);
      break;
    default:
      segments = parsePlain(rawText);
  }

  // Infer missing end times from next segment's start
  segments = inferEndTimes(segments);

  // Smart-merge if requested
  if (mergeGapSeconds > 0) {
    segments = smartMerge(segments, mergeGapSeconds);
  }

  // Build analytics
  const speakerStats = buildStats(segments);
  const speakers = Object.keys(speakerStats);

  // Total seconds = last segment end or last segment start
  let totalSeconds: number | null = null;
  if (segments.length > 0) {
    const last = segments[segments.length - 1];
    totalSeconds = last.end_seconds ?? last.start_seconds;
  }

  // Suggested primary = speaker with most speaking time, fallback to most words
  let suggestedPrimarySpeaker: string | null = null;
  if (speakers.length > 0) {
    const hasTimedData = Object.values(speakerStats).some(
      (s) => s.totalSeconds > 0
    );
    if (hasTimedData) {
      suggestedPrimarySpeaker = speakers.reduce((a, b) =>
        speakerStats[a].totalSeconds >= speakerStats[b].totalSeconds ? a : b
      );
    } else {
      suggestedPrimarySpeaker = speakers.reduce((a, b) =>
        speakerStats[a].wordCount >= speakerStats[b].wordCount ? a : b
      );
    }
  }

  return {
    segments,
    calculated: {
      totalSeconds,
      speakerStats,
      suggestedPrimarySpeaker,
      speakersDetected: speakers,
      segmentCount: segments.length,
    },
  };
}

