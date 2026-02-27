import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";

// GET /api/admin/qa-labels?transcriptId=...
// GET /api/admin/qa-labels?stats=1
export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);

  if (searchParams.get("stats") === "1") {
    const [totalYes, totalNo] = await Promise.all([
      prisma.qALabel.count({ where: { isQA: true } }),
      prisma.qALabel.count({ where: { isQA: false } }),
    ]);
    return NextResponse.json({ totalYes, totalNo, total: totalYes + totalNo });
  }

  const transcriptId = searchParams.get("transcriptId");
  if (!transcriptId) {
    return NextResponse.json(
      { error: "transcriptId query param is required" },
      { status: 400 }
    );
  }

  const labels = await prisma.qALabel.findMany({
    where: { transcriptId },
    orderBy: { created_at: "asc" },
  });

  return NextResponse.json(labels);
}

// POST /api/admin/qa-labels
// Body: { transcriptId, questionSpeaker, questionText, responseSpeaker, responseText, isQA, reasoning? }
// Upserts based on (transcriptId + questionText) to allow re-labeling.
export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const {
      transcriptId,
      questionSpeaker,
      questionText,
      responseSpeaker,
      responseText,
      isQA,
      reasoning,
    } = body;

    if (
      !transcriptId ||
      !questionSpeaker ||
      !questionText ||
      !responseSpeaker ||
      !responseText ||
      typeof isQA !== "boolean"
    ) {
      return NextResponse.json(
        {
          error:
            "Missing required fields: transcriptId, questionSpeaker, questionText, responseSpeaker, responseText, isQA",
        },
        { status: 400 }
      );
    }

    // Upsert — re-labeling the same exchange updates the existing record
    const existing = await prisma.qALabel.findFirst({
      where: { transcriptId, questionText },
    });

    let label;
    if (existing) {
      label = await prisma.qALabel.update({
        where: { id: existing.id },
        data: { isQA, reasoning: reasoning ?? null, updated_at: new Date() },
      });
    } else {
      label = await prisma.qALabel.create({
        data: {
          transcriptId,
          questionSpeaker,
          questionText,
          responseSpeaker,
          responseText,
          isQA,
          reasoning: reasoning ?? null,
        },
      });
    }

    return NextResponse.json({ id: label.id, isQA: label.isQA });
  } catch (err) {
    console.error("QA label error:", err);
    return NextResponse.json({ error: "Server error" }, { status: 500 });
  }
}
