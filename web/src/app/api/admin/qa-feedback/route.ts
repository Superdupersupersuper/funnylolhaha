import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";

/**
 * POST /api/admin/qa-feedback
 * Append a Q&A detection feedback event (removed / restored).
 * Body: { transcriptId, qaKey, action: "removed"|"restored", pairSnapshot }
 */
export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { transcriptId, qaKey, action, pairSnapshot } = body;

    if (!transcriptId || !qaKey || !action || !pairSnapshot) {
      return NextResponse.json(
        { error: "Missing required fields: transcriptId, qaKey, action, pairSnapshot" },
        { status: 400 }
      );
    }

    if (action !== "removed" && action !== "restored") {
      return NextResponse.json(
        { error: "action must be 'removed' or 'restored'" },
        { status: 400 }
      );
    }

    const feedback = await prisma.qADetectionFeedback.create({
      data: { transcriptId, qaKey, action, pairSnapshot },
    });

    return NextResponse.json({ id: feedback.id });
  } catch (err) {
    console.error("QA feedback error:", err);
    return NextResponse.json({ error: "Server error" }, { status: 500 });
  }
}
