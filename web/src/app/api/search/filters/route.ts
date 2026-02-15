import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";

/** GET /api/search/filters — returns available filter options. */
export async function GET() {
  try {
    const [speakers, themes, speechTypes] = await Promise.all([
      prisma.transcript.findMany({
        select: { primary_speaker: true },
        distinct: ["primary_speaker"],
        orderBy: { primary_speaker: "asc" },
      }),
      prisma.transcript.findMany({
        select: { key_themes: true },
      }),
      prisma.transcript.findMany({
        select: { speech_type: true },
        distinct: ["speech_type"],
        orderBy: { speech_type: "asc" },
      }),
    ]);

    // Flatten and dedupe themes
    const allThemes = new Set<string>();
    for (const t of themes) {
      for (const th of t.key_themes) allThemes.add(th);
    }

    return NextResponse.json({
      speakers: speakers.map((s) => s.primary_speaker),
      themes: Array.from(allThemes).sort(),
      speechTypes: speechTypes.map((s) => s.speech_type),
    });
  } catch (err) {
    console.error("Filters error:", err);
    return NextResponse.json({ error: "Server error" }, { status: 500 });
  }
}

