import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";

/** GET /api/search/filters — returns available filter options. */
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const [primarySpeakers, speakersPresent, themes, speechTypes] =
      await Promise.all([
      prisma.transcript.findMany({
        select: { primary_speaker: true },
        distinct: ["primary_speaker"],
        orderBy: { primary_speaker: "asc" },
      }),
      prisma.transcript.findMany({
        select: { speakers_present: true },
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

    // Combine primary_speaker + speakers_present into one deduped list.
    // Dedupe is case-insensitive, but we keep a stable display value.
    const speakerMap = new Map<string, string>();
    const addSpeaker = (name: string | null | undefined) => {
      const v = (name ?? "").trim();
      if (!v) return;
      const key = v.toLowerCase();
      if (!speakerMap.has(key)) speakerMap.set(key, v);
    };
    for (const s of primarySpeakers) addSpeaker(s.primary_speaker);
    for (const row of speakersPresent) {
      for (const s of row.speakers_present) addSpeaker(s);
    }
    const speakers = Array.from(speakerMap.values()).sort((a, b) =>
      a.localeCompare(b, undefined, { sensitivity: "base" })
    );

    return NextResponse.json({
      speakers,
      themes: Array.from(allThemes).sort(),
      speechTypes: speechTypes.map((s) => s.speech_type),
    }, {
      headers: {
        "Cache-Control": "no-store",
      },
    });
  } catch (err) {
    console.error("Filters error:", err);
    return NextResponse.json({ error: "Server error" }, { status: 500 });
  }
}

