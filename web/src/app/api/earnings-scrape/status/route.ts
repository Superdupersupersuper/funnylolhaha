import { NextResponse } from "next/server";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { resolve, join } from "node:path";

export const dynamic = "force-dynamic";

const OUT_DIR = resolve(process.cwd(), "tmp/earnings_scrape");

const ALL_TICKERS = [
  "HD","NVDA","SNOW","DELL","CAVA","RY","CELH","CRCL","HIMS","KTOS",
  "ORCL","FDX","COST","SBUX","DPZ","INTC","HOOD","ULTA","CMG","WMT","NKE","NFLX",
];

type EventType =
  | "ticker_start"
  | "discover_ok"
  | "upsert_ok"
  | "item_error"
  | "fallback_error"
  | "not_found"
  | "motleyfool_gap"
  | "parsed_dry_run"
  | "ticker_done"
  | "run_done";

interface LogEvent {
  type: EventType;
  ticker?: string;
  provider?: string;
  source?: string;
  source_url?: string;
  earnings_key?: string;
  title?: string;
  segmentCount?: number;
  transcriptId?: string;
  count?: number;
  error?: string;
  at: string;
}

export interface TickerStatus {
  ticker: string;
  state: "pending" | "running" | "done";
  discoveredCount: number;
  savedCount: number;
  errorCount: number;
  notFoundCount: number;
  transcripts: { key: string; title: string; segments: number; source: string }[];
  errors: { key: string; error: string }[];
}

export interface ScrapeStatus {
  runId: string;
  startedAt: string;
  logPath: string;
  isRunning: boolean;
  done: boolean;
  totalTickers: number;
  completedTickers: number;
  totalSaved: number;
  totalErrors: number;
  tickers: TickerStatus[];
  recentLog: string[];
}

function getLatestLogPath(): string | null {
  try {
    const files = readdirSync(OUT_DIR)
      .filter((f) => f.endsWith(".jsonl"))
      .map((f) => ({ f, mtime: statSync(join(OUT_DIR, f)).mtimeMs }))
      .sort((a, b) => b.mtime - a.mtime);
    return files.length ? join(OUT_DIR, files[0].f) : null;
  } catch {
    return null;
  }
}

function parseLog(path: string): ScrapeStatus {
  const raw = readFileSync(path, "utf8");
  const lines = raw.split("\n").filter(Boolean);
  const events: LogEvent[] = lines.flatMap((l) => {
    try { return [JSON.parse(l) as LogEvent]; } catch { return []; }
  });

  const runId = path.split("/").pop()!.replace("earnings-", "").replace(".jsonl", "");
  const startedAt = events.find((e) => e.type === "ticker_start")?.at ?? "";
  const done = events.some((e) => e.type === "run_done");

  // Build per-ticker state
  const tickerMap = new Map<string, TickerStatus>();
  for (const t of ALL_TICKERS) {
    tickerMap.set(t, {
      ticker: t,
      state: "pending",
      discoveredCount: 0,
      savedCount: 0,
      errorCount: 0,
      notFoundCount: 0,
      transcripts: [],
      errors: [],
    });
  }

  for (const e of events) {
    if (!e.ticker) continue;
    const ts = tickerMap.get(e.ticker) ?? {
      ticker: e.ticker,
      state: "pending" as const,
      discoveredCount: 0,
      savedCount: 0,
      errorCount: 0,
      notFoundCount: 0,
      transcripts: [],
      errors: [],
    };
    tickerMap.set(e.ticker, ts);

    switch (e.type) {
      case "ticker_start":
        ts.state = "running";
        break;
      case "discover_ok":
        ts.discoveredCount = e.count ?? 0;
        break;
      case "upsert_ok":
        ts.savedCount++;
        ts.transcripts.push({
          key: e.earnings_key ?? "",
          title: e.title ?? "",
          segments: e.segmentCount ?? 0,
          source: e.source ?? "",
        });
        break;
      case "item_error":
      case "fallback_error":
        ts.errorCount++;
        ts.errors.push({ key: e.earnings_key ?? e.source_url ?? "", error: e.error ?? "" });
        break;
      case "not_found":
        ts.notFoundCount++;
        break;
      case "ticker_done":
        ts.state = "done";
        break;
    }
  }

  const tickers = ALL_TICKERS.map((t) => tickerMap.get(t)!);
  const completedTickers = tickers.filter((t) => t.state === "done").length;
  const totalSaved = tickers.reduce((s, t) => s + t.savedCount, 0);
  const totalErrors = tickers.reduce((s, t) => s + t.errorCount, 0);

  // Last 30 meaningful log lines for the live feed
  const recentLog = events
    .filter((e) => ["upsert_ok", "item_error", "fallback_error", "not_found", "ticker_start", "ticker_done", "discover_ok"].includes(e.type))
    .slice(-30)
    .map((e) => {
      const t = new Date(e.at).toLocaleTimeString();
      switch (e.type) {
        case "ticker_start": return `${t} ▶ [${e.ticker}] starting…`;
        case "discover_ok": return `${t} 🔍 [${e.ticker}] found ${e.count} on Motley Fool`;
        case "upsert_ok": return `${t} ✓ [${e.ticker}] saved ${e.earnings_key} (${e.segmentCount} segs, ${e.source})`;
        case "item_error": return `${t} ✗ [${e.ticker}] error: ${e.error?.slice(0, 80)}`;
        case "fallback_error": return `${t} ✗ [${e.ticker}] fallback err: ${e.error?.slice(0, 80)}`;
        case "not_found": return `${t} — [${e.ticker}] ${e.earnings_key} not found anywhere`;
        case "ticker_done": return `${t} ✅ [${e.ticker}] done`;
        default: return "";
      }
    })
    .filter(Boolean);

  return {
    runId,
    startedAt,
    logPath: path,
    isRunning: !done,
    done,
    totalTickers: ALL_TICKERS.length,
    completedTickers,
    totalSaved,
    totalErrors,
    tickers,
    recentLog,
  };
}

export async function GET() {
  const logPath = getLatestLogPath();
  if (!logPath) {
    return NextResponse.json({ error: "No scrape log found. Has the scraper been run?" }, { status: 404 });
  }

  try {
    const status = parseLog(logPath);
    return NextResponse.json(status);
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}
