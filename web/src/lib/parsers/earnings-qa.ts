/**
 * Earnings-call Q&A detection
 *
 * Adapts the otter.ts analyzeQA pipeline to earnings calls where there are
 * multiple company representatives (CEO, CFO, Operator, etc.) who can
 * all serve as respondents. Anyone NOT in the company-rep set is treated
 * as an analyst / questioner.
 */

import type { ParsedSegment, QAPair, QAAnalytics } from "./otter";
import { computeQAAnalyticsFromPairs } from "./otter";

// ── Types ──────────────────────────────────────────────────────────────────

export interface EarningsQAResult {
  qa_data_auto: QAPair[];
  qa_data: QAPair[];
  question_count: number;
  avg_response_length_words: number | null;
  avg_response_length_seconds: number | null;
  has_q_and_a: boolean;
}

// ── Helpers ────────────────────────────────────────────────────────────────

function normName(n: string): string {
  return n.toLowerCase().replace(/[^a-z\s]/g, "").replace(/\s+/g, " ").trim();
}

function isCompanyRep(speaker: string, reps: Set<string>): boolean {
  if (reps.size === 0) return false;
  const norm = normName(speaker);
  if (!norm) return false;
  for (const rep of reps) {
    if (norm === rep) return true;
    if (norm.includes(rep) || rep.includes(norm)) return true;
  }
  return false;
}

function isLikelyEarningsQuestion(
  seg: ParsedSegment,
  companyReps: Set<string>
): boolean {
  if (isCompanyRep(seg.speaker, companyReps)) return false;
  if (/^operator$/i.test(seg.speaker)) return false;

  const text = seg.text;
  const textLower = text.toLowerCase().trim();
  const wordCount = text.split(/\s+/).length;

  if (wordCount < 8) return false;
  if (wordCount > 200) return false;

  const hasQuestionMark = text.includes("?");
  const startsWithInterrogative =
    /^(what|how|why|when|where|who|which|is|are|do|does|did|have|has|had|will|would|can|could|shall|should|may|might)\b/i.test(
      textLower
    );
  const hasDirectQuestion =
    /\b(can you|could you|would you|will you|do you|did you|have you|are you|is there|are there|i wonder|i'm wondering|i was wondering|i wanted to ask|what (is|are|was|were) your|what do you (think|believe|say|make)|how do you (feel|respond|react|see)|can you (tell|comment|explain|clarify|address|quantify|give|walk|talk|share|break|elaborate|help|provide))\b/i.test(
      textLower
    );

  if (!hasQuestionMark && !startsWithInterrogative && !hasDirectQuestion)
    return false;

  let score = 0;
  if (hasQuestionMark) score += 4;
  if (startsWithInterrogative) score += 3;
  if (hasDirectQuestion) score += 3;
  if (wordCount <= 80) score += 1;

  return score >= 4;
}

// ── Main entry ─────────────────────────────────────────────────────────────

/**
 * Detect Q&A pairs in an earnings-call transcript.
 *
 * @param segments   Speaking segments from the transcript
 * @param reps       Array of company representative names (from speakers_present)
 * @returns          Populated Q&A fields ready to persist on the Transcript record
 */
export function detectEarningsQA(
  segments: ParsedSegment[],
  reps: string[]
): EarningsQAResult {
  const companyReps = new Set(reps.map(normName).filter(Boolean));
  const pairs: QAPair[] = [];

  for (let i = 0; i < segments.length; i++) {
    const seg = segments[i];
    if (!isLikelyEarningsQuestion(seg, companyReps)) continue;

    // Collect consecutive company-rep response segments
    let mergedText = "";
    let mergedWordCount = 0;
    let responseStart: number | null = null;
    let responseSpeaker = "";
    let lastResponseIdx = -1;

    for (let j = i + 1; j < segments.length; j++) {
      const rseg = segments[j];
      const isRep = isCompanyRep(rseg.speaker, companyReps) ||
        /^operator$/i.test(rseg.speaker);

      if (!isRep) break;

      if (responseStart === null) {
        responseStart = rseg.start_seconds;
        responseSpeaker = rseg.speaker;
      }
      mergedText += (mergedText ? " " : "") + rseg.text;
      mergedWordCount += rseg.text.split(/\s+/).filter(Boolean).length;
      lastResponseIdx = j;
    }

    if (!mergedText || responseStart === null || mergedWordCount < 10) continue;

    // Skip if response looks like another question
    const respLower = mergedText.toLowerCase().trim();
    if (
      mergedText.trim().endsWith("?") ||
      /^(what|how|why|when|where|who|which|is|are|do|does|did)\b/i.test(
        respLower
      )
    )
      continue;

    let responseDuration: number | null = null;
    if (lastResponseIdx >= 0 && lastResponseIdx + 1 < segments.length) {
      responseDuration =
        segments[lastResponseIdx + 1].start_seconds - responseStart;
    } else if (
      lastResponseIdx >= 0 &&
      segments[lastResponseIdx].end_seconds !== null
    ) {
      responseDuration =
        (segments[lastResponseIdx].end_seconds as number) - responseStart;
    }

    pairs.push({
      qaKey: `${seg.speaker}:${seg.start_seconds}`,
      questionSpeaker: seg.speaker,
      questionText: seg.text,
      questionStart: seg.start_seconds,
      questionWordCount: seg.text.split(/\s+/).length,
      responseSpeaker,
      responseText: mergedText,
      responseStart,
      responseWordCount: mergedWordCount,
      responseDurationSeconds: responseDuration,
    });
  }

  const analytics = computeQAAnalyticsFromPairs(pairs);

  return {
    qa_data_auto: pairs,
    qa_data: pairs,
    question_count: analytics.questionCount,
    avg_response_length_words:
      analytics.avgResponseWords > 0 ? analytics.avgResponseWords : null,
    avg_response_length_seconds: analytics.avgResponseSeconds,
    has_q_and_a: pairs.length > 0,
  };
}
