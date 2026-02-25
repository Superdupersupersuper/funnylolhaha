import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";

export const dynamic = "force-dynamic";

/**
 * GET /api/earnings
 *   ?ticker=NVDA          – filter to one company
 *   ?ticker=NVDA,HD       – multiple tickers
 *   ?id=<transcriptId>    – get single transcript with segments
 */
export async function GET(req: NextRequest) {
  try {
    const sp = req.nextUrl.searchParams;
    const tickerParam = sp.get("ticker");
    const id = sp.get("id");

    // ── Single transcript with full segments ──────────────────────────────────
    if (id) {
      const t = await prisma.transcript.findUnique({
        where: { id },
        include: { segments: { orderBy: { start_seconds: "asc" } } },
      });
      if (!t) return NextResponse.json({ error: "Not found" }, { status: 404 });
      return NextResponse.json({ transcript: t });
    }

    // ── List: group by ticker ─────────────────────────────────────────────────
    const tickers = tickerParam
      ? tickerParam.split(",").map((t) => t.trim().toUpperCase()).filter(Boolean)
      : [];

    const where = {
      speech_type: "Earnings Call",
      // Exclude stale records that predate earnings_key support
      earnings_key: { not: null },
      ...(tickers.length ? { company_ticker: { in: tickers } } : {}),
    };

    const transcripts = await prisma.transcript.findMany({
      where,
      orderBy: [
        { company_ticker: "asc" },
        { fiscal_year: "desc" },
        { fiscal_quarter: "desc" },
      ],
      select: {
        id: true,
        title: true,
        event_date: true,
        company_ticker: true,
        fiscal_year: true,
        fiscal_quarter: true,
        primary_speaker: true,
        speakers_present: true,
        source: true,
        source_url: true,
        earnings_key: true,
        _count: { select: { segments: true } },
      },
    });

    // Group by ticker
    const grouped: Record<
      string,
      {
        ticker: string;
        transcripts: typeof transcripts;
      }
    > = {};

    for (const t of transcripts) {
      const key = t.company_ticker ?? "OTHER";
      if (!grouped[key]) grouped[key] = { ticker: key, transcripts: [] };
      grouped[key].transcripts.push(t);
    }

    const companies = Object.values(grouped).sort((a, b) =>
      a.ticker.localeCompare(b.ticker)
    );

    return NextResponse.json({ companies, total: transcripts.length });
  } catch (err) {
    console.error("Earnings API error:", err);
    return NextResponse.json({ error: "Server error" }, { status: 500 });
  }
}
