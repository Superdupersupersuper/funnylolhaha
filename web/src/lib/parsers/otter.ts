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

export interface QAPair {
  /** Stable identifier: `${questionSpeaker}:${questionStart}` or `manual:<timestamp>` */
  qaKey: string;
  questionSpeaker: string;
  questionText: string;
  questionStart: number;
  questionWordCount: number;
  responseSpeaker: string;
  responseText: string;
  responseStart: number;
  responseWordCount: number;
  responseDurationSeconds: number | null;
  /** True for pairs the user added manually (not auto-detected) */
  isManual?: boolean;
}

export interface QAAnalytics {
  questionCount: number;
  avgResponseWords: number;
  avgResponseSeconds: number | null;
  pairs: QAPair[];
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
  qaAnalytics?: QAAnalytics;
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

// ─── Q&A Detection ──────────────────────────────────────────────────────────

/**
 * Strict gating: a segment must have at least ONE strong syntactic question
 * signal before we even score it. This eliminates back-and-forth chatter
 * (e.g. "You can give me some", "There we go") that the old permissive scorer
 * would flag as questions.
 *
 * Calibrated for press conferences / interviews where questions can be:
 *  - Long multi-part queries (reporters often ask 80-150 word questions)
 *  - Statements ending in "?" after context-setting
 *  - Indirect questions ("I wonder if...", "I'd like to know...")
 *  - Questions addressed to a subject by title ("Mr. Mayor, ...")
 */
function isLikelyQuestion(segment: ParsedSegment, primarySpeaker: string | null): boolean {
  const text = segment.text;
  const textLower = text.toLowerCase().trim();
  const wordCount = text.split(/\s+/).length;

  // Must be a non-primary speaker
  if (primarySpeaker && segment.speaker === primarySpeaker) return false;

  // Skip very long segments — even multi-part press conf questions rarely exceed 150 words
  if (wordCount > 150) return false;

  // ── HARD GATE ─────────────────────────────────────────────────────────────
  // Need at least one strong syntactic signal of a genuine question.

  // 1. Literal question mark
  const hasQuestionMark = text.includes("?");

  // 2. Starts with an interrogative word (direct question form)
  const startsWithInterrogative = /^(what|how|why|when|where|who|which|is|are|do|does|did|have|has|had|will|would|can|could|shall|should|may|might)\b/i.test(textLower);

  // 3. Contains a directed question pattern — 2nd-person modal OR indirect question phrasing
  //    Covers: "can you tell us...", "I wonder what...", "I'd like to know...", etc.
  const hasDirectQuestion = /\b(can you|could you|would you|will you|do you|did you|have you|are you|is there|are there|i wonder|i'm wondering|i was wondering|i wanted to ask|i want to (ask|know)|i'd like to (ask|know)|can you (tell|comment|explain|clarify|address)|what (is|are|was|were) your|what('s| is) your|what do you (think|believe|say|make)|how do you (feel|respond|react|see)|what (are|were) the)\b/i.test(textLower);

  // Must hit at least one of the above — no strong signal → not a question
  if (!hasQuestionMark && !startsWithInterrogative && !hasDirectQuestion) return false;

  // ── ANTI-FALSE-POSITIVE FILTERS ───────────────────────────────────────────
  // Narrative / imperative patterns that often include question words but are
  // clearly not audience questions (common in speech/demonstration contexts).
  const isNarrative = /^(and (then|now|so|we|you|I|it|this|that|there)|there (we|you) go|look at (this|that)|we need|I need|put it|let('?s| us)|oh (look|and)|so (we|you|I)|just |maybe |we want|we can)\b/i.test(textLower);

  // If the only signal is a ? but it reads as a narrative/imperative, skip it
  if (isNarrative && !startsWithInterrogative && !hasDirectQuestion) return false;

  // Greetings / closings that happen to end with a ? (but let through if it also has a direct question)
  const isGreeting = /\b(thank you|thanks|good (morning|afternoon|evening)|hello|hi\b|bye|goodbye|great question)\b/i.test(textLower);
  if (isGreeting && !startsWithInterrogative && !hasDirectQuestion && !hasQuestionMark) return false;

  // ── REPORTER ADDRESS BONUS ────────────────────────────────────────────────
  // Reporters often address the subject by title before asking. This is a
  // reliable signal that the segment is a question in a press conference.
  const addressesSubject = /\b(mr\.|ms\.|mrs\.|mayor|commissioner|governor|president|secretary|senator|congressman|congresswoman|councilmember|chancellor|minister)\b/i.test(textLower);

  // ── CONFIDENCE SCORING ────────────────────────────────────────────────────
  let score = 0;
  if (hasQuestionMark) score += 4;
  if (startsWithInterrogative) score += 3;
  if (hasDirectQuestion) score += 3;
  if (addressesSubject) score += 2;
  if (wordCount <= 80) score += 1;
  if (isNarrative) score -= 3;
  if (isGreeting && !hasQuestionMark) score -= 2;

  // Lower threshold is fine because gating already eliminates most noise
  return score >= 4;
}

/** Compute aggregate analytics from an arbitrary subset of Q&A pairs. */
export function computeQAAnalyticsFromPairs(
  pairs: QAPair[]
): Pick<QAAnalytics, "questionCount" | "avgResponseWords" | "avgResponseSeconds"> {
  const questionCount = pairs.length;
  const avgResponseWords =
    pairs.length > 0
      ? Math.round(pairs.reduce((sum, p) => sum + p.responseWordCount, 0) / pairs.length)
      : 0;
  const responsesWithDuration = pairs.filter((p) => p.responseDurationSeconds !== null);
  const avgResponseSeconds =
    responsesWithDuration.length > 0
      ? Math.round(
          (responsesWithDuration.reduce(
            (sum, p) => sum + (p.responseDurationSeconds || 0),
            0
          ) /
            responsesWithDuration.length) *
            10
        ) / 10
      : null;
  return { questionCount, avgResponseWords, avgResponseSeconds };
}

/** Analyze Q&A patterns in the transcript segments. */
function analyzeQA(segments: ParsedSegment[], primarySpeaker: string | null): QAAnalytics {
  const pairs: QAPair[] = [];

  for (let i = 0; i < segments.length; i++) {
    const segment = segments[i];

    if (!isLikelyQuestion(segment, primarySpeaker)) continue;

    // ── Merge consecutive primary-speaker response segments ───────────────
    // Real Q&A answers often span multiple consecutive turns from the primary
    // speaker before the next questioner speaks again.
    let mergedText = "";
    let mergedWordCount = 0;
    let responseStart: number | null = null;
    let lastResponseIdx = -1;

    for (let j = i + 1; j < segments.length; j++) {
      const seg = segments[j];

      if (primarySpeaker) {
        // Stop collecting when another non-primary speaker takes the floor
        if (seg.speaker !== primarySpeaker) break;
        if (responseStart === null) responseStart = seg.start_seconds;
        mergedText += (mergedText ? " " : "") + seg.text;
        mergedWordCount += seg.text.split(/\s+/).length;
        lastResponseIdx = j;
      } else {
        // No primary speaker identified — take the immediately next segment only
        if (j === i + 1) {
          responseStart = seg.start_seconds;
          mergedText = seg.text;
          mergedWordCount = seg.text.split(/\s+/).length;
          lastResponseIdx = j;
        }
        break;
      }
    }

    // ── Validate the response ─────────────────────────────────────────────
    if (!mergedText || responseStart === null) continue;

    // Response must be substantive (not just a one-word acknowledgement)
    if (mergedWordCount < 15) continue;

    // Response should not itself look like a question
    const respLower = mergedText.toLowerCase().trim();
    if (
      mergedText.trim().endsWith("?") ||
      /^(what|how|why|when|where|who|which|is|are|do|does|did)\b/i.test(respLower)
    ) {
      continue;
    }

    // ── Duration ─────────────────────────────────────────────────────────
    let responseDuration: number | null = null;
    if (lastResponseIdx >= 0 && lastResponseIdx + 1 < segments.length) {
      responseDuration =
        segments[lastResponseIdx + 1].start_seconds - responseStart;
    } else if (lastResponseIdx >= 0 && segments[lastResponseIdx].end_seconds !== null) {
      responseDuration =
        (segments[lastResponseIdx].end_seconds as number) - responseStart;
    }

    const qaKey = `${segment.speaker}:${segment.start_seconds}`;

    pairs.push({
      qaKey,
      questionSpeaker: segment.speaker,
      questionText: segment.text,
      questionStart: segment.start_seconds,
      questionWordCount: segment.text.split(/\s+/).length,
      responseSpeaker: primarySpeaker ?? segments[lastResponseIdx]?.speaker ?? "",
      responseText: mergedText,
      responseStart,
      responseWordCount: mergedWordCount,
      responseDurationSeconds: responseDuration,
    });
  }

  return {
    ...computeQAAnalyticsFromPairs(pairs),
    pairs,
  };
}

// ─── Candidate exchange extractor ────────────────────────────────────────────

export interface CandidateExchange {
  /** Stable key: `${questionSpeaker}:${questionStart}` */
  qaKey: string;
  questionSpeaker: string;
  questionText: string;
  questionStart: number;
  responseSpeaker: string;
  responseText: string;
  responseStart: number;
  responseWordCount: number;
}

/**
 * Extracts every candidate Q&A exchange from a list of segments: any
 * non-primary-speaker turn (≥ 10 words) immediately followed by one or more
 * consecutive primary-speaker segments.
 *
 * Used by:
 *  – the labeling UI to generate flashcard candidates
 *  – the AI classifier to determine which exchanges to evaluate
 */
export function extractCandidateExchanges(
  segments: ParsedSegment[],
  primarySpeaker: string | null
): CandidateExchange[] {
  const candidates: CandidateExchange[] = [];

  for (let i = 0; i < segments.length; i++) {
    const seg = segments[i];

    // Skip primary speaker and very short segments
    if (primarySpeaker && seg.speaker === primarySpeaker) continue;
    const wordCount = seg.text.split(/\s+/).filter(Boolean).length;
    if (wordCount < 10) continue;

    // Collect the following primary-speaker response block
    let mergedText = "";
    let mergedWordCount = 0;
    let responseStart: number | null = null;

    for (let j = i + 1; j < segments.length; j++) {
      const rseg = segments[j];
      if (primarySpeaker) {
        if (rseg.speaker !== primarySpeaker) break;
        if (responseStart === null) responseStart = rseg.start_seconds;
        mergedText += (mergedText ? " " : "") + rseg.text;
        mergedWordCount += rseg.text.split(/\s+/).filter(Boolean).length;
      } else {
        // No primary speaker — take the immediately next segment only
        if (j === i + 1) {
          responseStart = rseg.start_seconds;
          mergedText = rseg.text;
          mergedWordCount = rseg.text.split(/\s+/).filter(Boolean).length;
        }
        break;
      }
    }

    if (!mergedText || responseStart === null || mergedWordCount < 10) continue;

    candidates.push({
      qaKey: `${seg.speaker}:${seg.start_seconds}`,
      questionSpeaker: seg.speaker,
      questionText: seg.text,
      questionStart: seg.start_seconds,
      responseSpeaker: primarySpeaker ?? "",
      responseText: mergedText,
      responseStart,
      responseWordCount: mergedWordCount,
    });
  }

  return candidates;
}

// ─── Main entry ─────────────────────────────────────────────────────────────

export interface ParseOptions {
  /** Merge consecutive same-speaker segments when gap <= this many seconds. Set 0 to disable. */
  mergeGapSeconds?: number;
  /** Analyze Q&A patterns (requires has_q_and_a to be true). */
  detectQA?: boolean;
}

export function parseOtterTranscript(
  rawText: string,
  options: ParseOptions = {}
): ParseResult {
  const { mergeGapSeconds = 3, detectQA = false } = options;

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

  // Q&A analysis if requested
  let qaAnalytics: QAAnalytics | undefined;
  if (detectQA) {
    qaAnalytics = analyzeQA(segments, suggestedPrimarySpeaker);
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
    qaAnalytics,
  };
}

