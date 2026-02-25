"use client";

import { useEffect, useRef, useState } from "react";

interface TickerStatus {
  ticker: string;
  state: "pending" | "running" | "done";
  discoveredCount: number;
  savedCount: number;
  errorCount: number;
  notFoundCount: number;
  transcripts: { key: string; title: string; segments: number; source: string }[];
  errors: { key: string; error: string }[];
}

interface ScrapeStatus {
  runId: string;
  startedAt: string;
  isRunning: boolean;
  done: boolean;
  totalTickers: number;
  completedTickers: number;
  totalSaved: number;
  totalErrors: number;
  tickers: TickerStatus[];
  recentLog: string[];
}

const SOURCE_COLOR: Record<string, string> = {
  motleyfool: "text-emerald-400",
  insidermonkey: "text-sky-400",
};

function Badge({ children, color }: { children: React.ReactNode; color: string }) {
  return (
    <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wide ${color}`}>
      {children}
    </span>
  );
}

function StateIndicator({ state }: { state: TickerStatus["state"] }) {
  if (state === "done") return <span className="text-emerald-400 text-xs font-bold">✓ Done</span>;
  if (state === "running") return (
    <span className="flex items-center gap-1 text-amber-400 text-xs font-bold">
      <span className="animate-pulse">●</span> Running
    </span>
  );
  return <span className="text-zinc-500 text-xs">Pending</span>;
}

function ProgressBar({ value, max, color = "bg-emerald-500" }: { value: number; max: number; color?: string }) {
  const pct = max === 0 ? 0 : Math.min(100, (value / max) * 100);
  return (
    <div className="h-1.5 w-full bg-zinc-800 rounded-full overflow-hidden">
      <div className={`h-full rounded-full transition-all duration-500 ${color}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

export default function EarningsScrapeMonitor() {
  const [status, setStatus] = useState<ScrapeStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [expandedTicker, setExpandedTicker] = useState<string | null>(null);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let active = true;

    async function poll() {
      try {
        const res = await fetch("/api/earnings-scrape/status", { cache: "no-store" });
        if (!res.ok) {
          const j = await res.json().catch(() => ({}));
          setError(j.error ?? `HTTP ${res.status}`);
          return;
        }
        const data: ScrapeStatus = await res.json();
        if (active) {
          setStatus(data);
          setError(null);
          setLastUpdated(new Date());
        }
      } catch (e) {
        if (active) setError(String(e));
      }
    }

    poll();
    const interval = setInterval(poll, 4000);
    return () => { active = false; clearInterval(interval); };
  }, []);

  // Auto-scroll log to bottom
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [status?.recentLog]);

  if (error) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center text-red-400 p-8">
        <div className="text-center space-y-2">
          <p className="text-2xl font-bold">Error</p>
          <p className="text-sm opacity-70">{error}</p>
        </div>
      </div>
    );
  }

  if (!status) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <div className="text-zinc-500 text-sm animate-pulse">Loading scrape status…</div>
      </div>
    );
  }

  const overallPct = Math.round((status.completedTickers / status.totalTickers) * 100);
  const startTime = status.startedAt ? new Date(status.startedAt) : null;
  const elapsed = startTime ? Math.floor((Date.now() - startTime.getTime()) / 1000) : 0;
  const elapsedStr =
    elapsed < 60 ? `${elapsed}s` :
    elapsed < 3600 ? `${Math.floor(elapsed / 60)}m ${elapsed % 60}s` :
    `${Math.floor(elapsed / 3600)}h ${Math.floor((elapsed % 3600) / 60)}m`;

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 p-6 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Earnings Scraper</h1>
          <p className="text-zinc-500 text-sm mt-0.5">
            Run ID: <span className="font-mono text-zinc-400 text-xs">{status.runId}</span>
          </p>
        </div>
        <div className="text-right space-y-1">
          <div className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-sm font-semibold ${status.done ? "bg-emerald-900/50 text-emerald-400" : "bg-amber-900/40 text-amber-400"}`}>
            {status.done ? "✅ Complete" : <><span className="animate-pulse">●</span> Running</>}
          </div>
          {lastUpdated && (
            <p className="text-zinc-600 text-xs">Updated {lastUpdated.toLocaleTimeString()}</p>
          )}
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "Tickers Done", value: `${status.completedTickers} / ${status.totalTickers}`, sub: `${overallPct}% complete` },
          { label: "Transcripts Saved", value: status.totalSaved, sub: "to database" },
          { label: "Errors", value: status.totalErrors, sub: "fetch / parse failures" },
          { label: "Elapsed", value: elapsedStr, sub: startTime ? `started ${startTime.toLocaleTimeString()}` : "—" },
        ].map((c) => (
          <div key={c.label} className="bg-zinc-900 rounded-xl p-4 border border-zinc-800">
            <p className="text-zinc-500 text-xs uppercase tracking-wide mb-1">{c.label}</p>
            <p className="text-2xl font-bold tabular-nums">{c.value}</p>
            <p className="text-zinc-600 text-xs mt-1">{c.sub}</p>
          </div>
        ))}
      </div>

      {/* Overall progress bar */}
      <div className="bg-zinc-900 rounded-xl p-4 border border-zinc-800 space-y-2">
        <div className="flex justify-between text-xs text-zinc-500">
          <span>Overall progress</span>
          <span>{overallPct}%</span>
        </div>
        <div className="h-3 bg-zinc-800 rounded-full overflow-hidden">
          <div
            className="h-full rounded-full bg-gradient-to-r from-emerald-600 to-emerald-400 transition-all duration-700"
            style={{ width: `${overallPct}%` }}
          />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Ticker grid */}
        <div className="lg:col-span-2 space-y-3">
          <h2 className="text-sm font-semibold text-zinc-400 uppercase tracking-wide">Tickers</h2>
          <div className="space-y-2">
            {status.tickers.map((t) => (
              <div key={t.ticker} className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
                {/* Summary row */}
                <button
                  className="w-full flex items-center gap-4 px-4 py-3 text-left hover:bg-zinc-800/50 transition-colors"
                  onClick={() => setExpandedTicker(expandedTicker === t.ticker ? null : t.ticker)}
                >
                  {/* Ticker name */}
                  <span className="font-mono font-bold text-sm w-12 shrink-0">{t.ticker}</span>

                  {/* State badge */}
                  <span className="w-20 shrink-0">
                    <StateIndicator state={t.state} />
                  </span>

                  {/* Progress bar */}
                  <div className="flex-1 min-w-0">
                    <ProgressBar
                      value={t.savedCount}
                      max={Math.max(t.discoveredCount + (t.savedCount - t.discoveredCount), t.savedCount, 1)}
                      color={t.errorCount > 0 ? "bg-amber-500" : "bg-emerald-500"}
                    />
                  </div>

                  {/* Counts */}
                  <div className="flex gap-3 text-xs tabular-nums shrink-0">
                    <span className="text-emerald-400 font-semibold">{t.savedCount} saved</span>
                    {t.errorCount > 0 && <span className="text-red-400">{t.errorCount} err</span>}
                    {t.notFoundCount > 0 && <span className="text-zinc-500">{t.notFoundCount} missing</span>}
                  </div>

                  <span className="text-zinc-600 text-xs">{expandedTicker === t.ticker ? "▲" : "▼"}</span>
                </button>

                {/* Expanded details */}
                {expandedTicker === t.ticker && (
                  <div className="border-t border-zinc-800 px-4 py-3 space-y-2">
                    {t.transcripts.length > 0 ? (
                      <div className="space-y-1">
                        {t.transcripts.map((tr) => (
                          <div key={tr.key} className="flex items-center justify-between text-xs">
                            <span className="font-mono text-zinc-300">{tr.key}</span>
                            <div className="flex items-center gap-2 text-zinc-500">
                              <span>{tr.segments} segs</span>
                              <Badge color={SOURCE_COLOR[tr.source] ?? "text-zinc-400"}>
                                {tr.source === "motleyfool" ? "Fool" : tr.source === "insidermonkey" ? "IM" : tr.source}
                              </Badge>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : t.state === "pending" ? (
                      <p className="text-zinc-600 text-xs">Not started yet</p>
                    ) : (
                      <p className="text-zinc-600 text-xs">No transcripts saved yet</p>
                    )}
                    {t.errors.map((err, i) => (
                      <div key={i} className="text-red-400 text-xs bg-red-950/30 rounded px-2 py-1">
                        {err.key}: {err.error.slice(0, 120)}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Live log */}
        <div className="space-y-3">
          <h2 className="text-sm font-semibold text-zinc-400 uppercase tracking-wide">Live Activity</h2>
          <div
            ref={logRef}
            className="bg-zinc-900 border border-zinc-800 rounded-xl p-3 h-[600px] overflow-y-auto font-mono text-xs space-y-1 scroll-smooth"
          >
            {status.recentLog.length === 0 ? (
              <p className="text-zinc-600 italic">Waiting for events…</p>
            ) : (
              status.recentLog.map((line, i) => {
                const isError = line.includes("✗");
                const isDone = line.includes("✅");
                const isOk = line.includes("✓");
                return (
                  <p
                    key={i}
                    className={
                      isError ? "text-red-400" :
                      isDone ? "text-emerald-400 font-semibold" :
                      isOk ? "text-zinc-200" :
                      "text-zinc-500"
                    }
                  >
                    {line}
                  </p>
                );
              })
            )}
            {status.isRunning && (
              <p className="text-zinc-600 animate-pulse">● polling every 4s…</p>
            )}
          </div>
        </div>
      </div>

      {/* Legend */}
      <div className="flex gap-4 text-xs text-zinc-600 pt-2">
        <span><span className="text-emerald-400">Fool</span> = Motley Fool</span>
        <span><span className="text-sky-400">IM</span> = InsiderMonkey</span>
        <span>Refreshes automatically every 4 seconds</span>
      </div>
    </div>
  );
}
