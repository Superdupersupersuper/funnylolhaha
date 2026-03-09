"use client";

import { useEffect, useState, useCallback } from "react";
import Nav from "@/components/Nav";

interface TranscriptSummary {
  id: string;
  title: string;
  event_date: string;
  company_ticker: string | null;
  fiscal_year: number | null;
  fiscal_quarter: number | null;
  primary_speaker: string;
  speakers_present: string[];
  source: string | null;
  source_url: string | null;
  earnings_key: string | null;
  _count: { segments: number };
}

interface Company {
  ticker: string;
  transcripts: TranscriptSummary[];
}

interface TranscriptDetail {
  id: string;
  title: string;
  event_date: string;
  company_ticker: string | null;
  fiscal_year: number | null;
  fiscal_quarter: number | null;
  primary_speaker: string;
  speakers_present: string[];
  segments: { speaker: string; start_seconds: number; text: string }[];
}

const COMPANY_NAMES: Record<string, string> = {
  HD: "Home Depot",
  NVDA: "NVIDIA",
  SNOW: "Snowflake",
  DELL: "Dell Technologies",
  CAVA: "CAVA Group",
  RY: "Royal Bank of Canada",
  CELH: "Celsius Holdings",
  CRCL: "Circle Internet",
  HIMS: "Hims & Hers",
  KTOS: "Kratos Defense",
  ORCL: "Oracle",
  FDX: "FedEx",
  COST: "Costco",
  SBUX: "Starbucks",
  DPZ: "Domino's Pizza",
  INTC: "Intel",
  HOOD: "Robinhood",
  ULTA: "Ulta Beauty",
  CMG: "Chipotle",
  WMT: "Walmart",
  NKE: "Nike",
  NFLX: "Netflix",
};

function SourceBadge({ source }: { source: string | null }) {
  if (source === "motleyfool")
    return <span className="rounded bg-emerald-900/40 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-400">Fool</span>;
  if (source === "insidermonkey")
    return <span className="rounded bg-sky-900/40 px-1.5 py-0.5 text-[10px] font-semibold text-sky-400">IM</span>;
  return null;
}

function QuarterLabel({ fy, fq }: { fy: number | null; fq: number | null }) {
  if (!fy || !fq) return <span className="text-zinc-500">—</span>;
  return <span className="font-mono font-semibold">Q{fq} FY{fy}</span>;
}

function TranscriptViewer({
  transcript,
  onClose,
}: {
  transcript: TranscriptDetail;
  onClose: () => void;
}) {
  const companyNames = new Set(transcript.speakers_present.map((s) => s.toLowerCase()));
  const isCompany = (speaker: string) => {
    const norm = speaker.toLowerCase().trim();
    return (
      companyNames.size === 0 ||
      companyNames.has(norm) ||
      Array.from(companyNames).some(
        (n) => norm.includes(n.split(" ")[0]) || n.includes(norm.split(" ")[0])
      )
    );
  };

  const [activeSection, setActiveSection] = useState<"all" | "company" | "qa">("all");
  const filtered = transcript.segments.filter((s) => {
    if (activeSection === "company") return isCompany(s.speaker);
    if (activeSection === "qa") return !isCompany(s.speaker);
    return true;
  });

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-zinc-950">
      {/* Header */}
      <div className="flex items-start justify-between border-b border-zinc-800 px-6 py-4">
        <div>
          <h2 className="text-lg font-bold">{transcript.title}</h2>
          <div className="mt-1 flex gap-3 text-xs text-zinc-500">
            <span>{new Date(transcript.event_date).toLocaleDateString()}</span>
            <QuarterLabel fy={transcript.fiscal_year} fq={transcript.fiscal_quarter} />
            <span>{transcript.segments.length} segments</span>
          </div>
          {transcript.speakers_present.length > 0 && (
            <div className="mt-1 text-xs text-zinc-600">
              Company reps: {transcript.speakers_present.join(", ")}
            </div>
          )}
        </div>
        <button
          onClick={onClose}
          className="rounded-full p-2 text-zinc-400 hover:bg-zinc-800 hover:text-white"
        >
          ✕
        </button>
      </div>

      {/* Section tabs */}
      <div className="flex gap-2 border-b border-zinc-800 px-6 py-2">
        {(["all", "company", "qa"] as const).map((s) => (
          <button
            key={s}
            onClick={() => setActiveSection(s)}
            className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
              activeSection === s
                ? "bg-zinc-700 text-white"
                : "text-zinc-500 hover:text-zinc-300"
            }`}
          >
            {s === "all" ? "All" : s === "company" ? "Company only" : "Q&A callers"}
          </button>
        ))}
      </div>

      {/* Segments */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-3">
        {filtered.map((seg, i) => {
          const company = isCompany(seg.speaker);
          return (
            <div key={i} className={`rounded-lg p-3 ${company ? "bg-zinc-900" : "bg-zinc-900/50"}`}>
              <div className="mb-1 flex items-center gap-2">
                <span className={`text-sm font-semibold ${company ? "text-blue-400" : "text-amber-400"}`}>
                  {seg.speaker}
                </span>
                {!company && (
                  <span className="rounded bg-amber-900/30 px-1.5 py-0.5 text-[10px] font-bold uppercase text-amber-400">
                    Caller
                  </span>
                )}
              </div>
              <p className="text-sm leading-relaxed text-zinc-300">{seg.text}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function EarningsPage() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [openTranscript, setOpenTranscript] = useState<TranscriptDetail | null>(null);
  const [loadingId, setLoadingId] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/earnings")
      .then((r) => r.json())
      .then((d) => {
        setCompanies(d.companies || []);
        setTotal(d.total || 0);
      })
      .finally(() => setLoading(false));
  }, []);

  const openViewer = useCallback(async (id: string) => {
    setLoadingId(id);
    try {
      const res = await fetch(`/api/earnings?id=${id}`);
      const data = await res.json();
      if (data.transcript) setOpenTranscript(data.transcript);
    } finally {
      setLoadingId(null);
    }
  }, []);

  const toggleCompany = (ticker: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(ticker)) next.delete(ticker);
      else next.add(ticker);
      return next;
    });
  };

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-950 text-zinc-500">
        Loading earnings calls…
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <Nav active="earnings" />

      {openTranscript && (
        <TranscriptViewer
          transcript={openTranscript}
          onClose={() => setOpenTranscript(null)}
        />
      )}

      <div className="mx-auto max-w-4xl px-4 py-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold tracking-tight">Earnings Calls</h1>
          <p className="mt-1 text-zinc-500 text-sm">
            {total} transcripts across {companies.length} companies · back to FY2020
          </p>
        </div>

        {companies.length === 0 ? (
          <div className="rounded-xl border border-dashed border-zinc-800 p-12 text-center text-zinc-600">
            No earnings call transcripts yet.
          </div>
        ) : (
          <div className="space-y-3">
            {companies.map(({ ticker, transcripts }) => {
              const isOpen = expanded.has(ticker);
              const name = COMPANY_NAMES[ticker] ?? ticker;
              const latest = transcripts[0];

              return (
                <div key={ticker} className="rounded-xl border border-zinc-800 bg-zinc-900 overflow-hidden">
                  {/* Company header row */}
                  <button
                    className="flex w-full items-center justify-between px-5 py-4 hover:bg-zinc-800/50 transition-colors text-left"
                    onClick={() => toggleCompany(ticker)}
                  >
                    <div className="flex items-center gap-4">
                      <span className="w-14 font-mono text-sm font-bold text-zinc-300">{ticker}</span>
                      <span className="text-base font-semibold">{name}</span>
                    </div>
                    <div className="flex items-center gap-4 text-sm text-zinc-500">
                      <span>{transcripts.length} quarter{transcripts.length !== 1 ? "s" : ""}</span>
                      {latest && (
                        <span className="text-xs">
                          Latest: <QuarterLabel fy={latest.fiscal_year} fq={latest.fiscal_quarter} />
                        </span>
                      )}
                      <span className="text-zinc-600">{isOpen ? "▲" : "▼"}</span>
                    </div>
                  </button>

                  {/* Transcript list */}
                  {isOpen && (
                    <div className="border-t border-zinc-800 divide-y divide-zinc-800/60">
                      {transcripts.map((t) => (
                        <button
                          key={t.id}
                          onClick={() => openViewer(t.id)}
                          disabled={loadingId === t.id}
                          className="flex w-full items-center justify-between px-5 py-3 hover:bg-zinc-800/40 transition-colors text-left group"
                        >
                          <div className="flex items-center gap-4">
                            <div className="w-20">
                              <QuarterLabel fy={t.fiscal_year} fq={t.fiscal_quarter} />
                            </div>
                            <div className="text-sm text-zinc-400">
                              {new Date(t.event_date).toLocaleDateString("en-US", {
                                year: "numeric",
                                month: "short",
                                day: "numeric",
                              })}
                            </div>
                            {t.speakers_present.length > 0 && (
                              <div className="hidden md:flex gap-1 text-xs text-zinc-600">
                                {t.speakers_present.slice(0, 3).map((s) => (
                                  <span key={s} className="rounded bg-zinc-800 px-1.5 py-0.5">{s.split(" ").slice(-1)[0]}</span>
                                ))}
                              </div>
                            )}
                          </div>
                          <div className="flex items-center gap-3 text-sm text-zinc-500">
                            <span>{t._count.segments} segs</span>
                            <SourceBadge source={t.source} />
                            <span className="rounded-full border border-zinc-700 px-2.5 py-0.5 text-xs text-zinc-400 group-hover:border-zinc-500 group-hover:text-zinc-300 transition-colors">
                              {loadingId === t.id ? "Loading…" : "View →"}
                            </span>
                          </div>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
