import { NextRequest, NextResponse } from "next/server";
import OpenAI from "openai";
import { prisma } from "@/lib/db";
import type { CandidateExchange } from "@/lib/parsers/otter";

const MIN_LABELS_REQUIRED = 10; // minimum labeled examples before AI is used

export interface ClassifyResult {
  qaKey: string;
  isQA: boolean;
  confidence: number; // 0–1
  reason: string;
}

/**
 * POST /api/admin/qa-classify
 *
 * Accepts a list of candidate exchanges and classifies each one using
 * OpenAI gpt-4o-mini, with human-labeled examples as few-shot prompts.
 *
 * Body: { candidates: CandidateExchange[], primarySpeaker: string }
 * Returns: { results: ClassifyResult[], usedAI: boolean }
 *
 * If OPENAI_API_KEY is not set or there aren't enough labels yet,
 * returns usedAI: false so the caller can fall back to the heuristic.
 */
export async function POST(req: NextRequest) {
  const apiKey = process.env.OPENAI_API_KEY;

  if (!apiKey) {
    return NextResponse.json({ usedAI: false, results: [] });
  }

  try {
    const body = await req.json();
    const candidates: CandidateExchange[] = body.candidates ?? [];
    const primarySpeaker: string = body.primarySpeaker ?? "";

    if (candidates.length === 0) {
      return NextResponse.json({ usedAI: false, results: [] });
    }

    // Load few-shot examples from the database
    const [yesLabels, noLabels] = await Promise.all([
      prisma.qALabel.findMany({
        where: { isQA: true },
        orderBy: { created_at: "desc" },
        take: 12,
        select: {
          questionSpeaker: true,
          questionText: true,
          responseSpeaker: true,
          responseText: true,
          isQA: true,
          reasoning: true,
        },
      }),
      prisma.qALabel.findMany({
        where: { isQA: false },
        orderBy: { created_at: "desc" },
        take: 12,
        select: {
          questionSpeaker: true,
          questionText: true,
          responseSpeaker: true,
          responseText: true,
          isQA: true,
          reasoning: true,
        },
      }),
    ]);

    const totalLabels = yesLabels.length + noLabels.length;
    if (totalLabels < MIN_LABELS_REQUIRED) {
      return NextResponse.json({
        usedAI: false,
        results: [],
        message: `Need at least ${MIN_LABELS_REQUIRED} labeled examples (have ${totalLabels}).`,
      });
    }

    // Interleave yes/no examples for balanced few-shot prompt
    const examples = interleave(yesLabels, noLabels);

    const systemPrompt = buildSystemPrompt(primarySpeaker, examples);
    const userPrompt = buildUserPrompt(candidates);

    const client = new OpenAI({ apiKey });

    const completion = await client.chat.completions.create({
      model: "gpt-4o-mini",
      temperature: 0,
      response_format: { type: "json_object" },
      messages: [
        { role: "system", content: systemPrompt },
        { role: "user", content: userPrompt },
      ],
    });

    const raw = completion.choices[0]?.message?.content ?? "{}";
    const parsed = JSON.parse(raw) as {
      results?: Array<{
        qaKey: string;
        isQA: boolean;
        confidence: number;
        reason: string;
      }>;
    };

    const results: ClassifyResult[] = (parsed.results ?? []).map((r) => ({
      qaKey: r.qaKey,
      isQA: Boolean(r.isQA),
      confidence: typeof r.confidence === "number" ? Math.min(1, Math.max(0, r.confidence)) : 0.5,
      reason: r.reason ?? "",
    }));

    return NextResponse.json({ usedAI: true, results });
  } catch (err) {
    console.error("QA classify error:", err);
    return NextResponse.json(
      { error: "Classification failed", usedAI: false, results: [] },
      { status: 500 }
    );
  }
}

// ─── Prompt builders ─────────────────────────────────────────────────────────

type LabelExample = {
  questionSpeaker: string;
  questionText: string;
  responseSpeaker: string;
  responseText: string;
  isQA: boolean;
  reasoning: string | null;
};

function buildSystemPrompt(primarySpeaker: string, examples: LabelExample[]): string {
  const fewShot = examples
    .map(
      (ex, i) =>
        `Example ${i + 1}:
  Question speaker: ${ex.questionSpeaker}
  Question: "${truncate(ex.questionText, 80)}"
  Response speaker: ${ex.responseSpeaker}
  Response: "${truncate(ex.responseText, 80)}"
  Label: ${ex.isQA ? "YES — genuine Q&A" : "NO — not Q&A"}${ex.reasoning ? `\n  Reason: ${ex.reasoning}` : ""}`
    )
    .join("\n\n");

  return `You are an expert at identifying genuine Q&A exchanges in political press conferences, interviews, and public speeches.

PRIMARY SPEAKER being questioned: "${primarySpeaker}"

WHAT COUNTS AS Q&A:
- A reporter or audience member asks a direct, substantive question about policy, events, or the primary speaker's actions/views
- The primary speaker gives a genuine answer (not just a transition or filler phrase)
- The question has clear interrogative intent — whether or not it ends with a question mark

WHAT DOES NOT COUNT AS Q&A:
- Conversational back-and-forth without a real question (e.g. "Thank you, great, okay")
- The moderator redirecting the floor or introducing someone
- The primary speaker summarizing or repeating something said by another speaker
- Short filler exchanges ("Yeah", "Right", "Exactly") even if followed by a real response
- A question asked to someone other than the primary speaker

LABELED EXAMPLES FROM HUMAN TRAINER:
${fewShot}

Your task: Classify each candidate exchange below as Q&A or not Q&A.
Return a JSON object with this exact shape:
{
  "results": [
    {
      "qaKey": "<exact qaKey from input>",
      "isQA": true | false,
      "confidence": 0.0–1.0,
      "reason": "<brief one-sentence explanation>"
    }
  ]
}`;
}

function buildUserPrompt(candidates: CandidateExchange[]): string {
  const items = candidates
    .map(
      (c, i) =>
        `Candidate ${i + 1}:
  qaKey: "${c.qaKey}"
  Question speaker: ${c.questionSpeaker}
  Question: "${truncate(c.questionText, 120)}"
  Response speaker: ${c.responseSpeaker}
  Response: "${truncate(c.responseText, 120)}"`
    )
    .join("\n\n");

  return `Classify each of the following ${candidates.length} candidate exchange(s):\n\n${items}`;
}

function truncate(text: string, words: number): string {
  const parts = text.split(/\s+/);
  if (parts.length <= words) return text;
  return parts.slice(0, words).join(" ") + "…";
}

function interleave<T>(a: T[], b: T[]): T[] {
  const result: T[] = [];
  const len = Math.max(a.length, b.length);
  for (let i = 0; i < len; i++) {
    if (i < a.length) result.push(a[i]);
    if (i < b.length) result.push(b[i]);
  }
  return result;
}
