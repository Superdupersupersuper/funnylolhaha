"use client";

import { useState, useEffect, useCallback } from "react";
import { secondsToTime } from "@/lib/parsers/otter";
import Nav from "@/components/Nav";

interface SearchResult {
  transcript: {
    id: string;
    title: string;
    event_date: string;
    speech_type: string;
    primary_speaker: string;
    key_themes: string[];
    has_q_and_a: boolean;
    total_speech_length_seconds: number | null;
  };
  mentionCount: number;
  segments: {
    speaker: string;
    start_seconds: number;
    text: string;
    highlighted: string;
    isPrimary: boolean;
  }[];
}

interface Filters {
  speakers: string[];
  themes: string[];
  speechTypes: string[];
}

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [totalMentions, setTotalMentions] = useState(0);
  const [totalTranscripts, setTotalTranscripts] = useState(0);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);

  // Filters
  const [filters, setFilters] = useState<Filters>({
    speakers: [],
    themes: [],
    speechTypes: [],
  });
  const [speaker, setSpeaker] = useState("");
  const [theme, setTheme] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  // Expanded segments
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  const loadFilters = useCallback(async () => {
    try {
      const r = await fetch("/api/search/filters", { cache: "no-store" });
      const data = await r.json();
      if (data?.speakers) setFilters(data);
    } catch {
      // ignore
    }
  }, []);

  // Fetch filter options on mount
  useEffect(() => {
    loadFilters();
  }, [loadFilters]);

  const doSearch = useCallback(async () => {
    if (!query.trim()) return;
    setLoading(true);
    setSearched(true);

    const params = new URLSearchParams({ q: query });
    if (speaker) params.set("speaker", speaker);
    if (theme) params.set("theme", theme);
    if (startDate) params.set("start", startDate);
    if (endDate) params.set("end", endDate);

    try {
      const res = await fetch(`/api/search?${params}`);
      const data = await res.json();
      setResults(data.results || []);
      setTotalMentions(data.totalMentions || 0);
      setTotalTranscripts(data.totalTranscripts || 0);
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, [query, speaker, theme, startDate, endDate]);

  function toggleExpand(id: string) {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <div className="min-h-screen">
      <Nav active="search" />
      <div className="mx-auto max-w-5xl px-4 py-8">
      <h1 className="mb-6 text-3xl font-bold tracking-tight">
        MentionMarkets Search
      </h1>

      {/* Search bar */}
      <div className="flex gap-2">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && doSearch()}
          placeholder="Search keyword across all transcripts…"
          className="flex-1 rounded-md border border-input bg-background px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          autoFocus
        />
        <button
          onClick={doSearch}
          disabled={loading || !query.trim()}
          className="rounded-md bg-primary px-6 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          {loading ? "Searching…" : "Search"}
        </button>
      </div>

      {/* Filters */}
      <div className="mt-4 flex flex-wrap items-end gap-3">
        {filters.speakers.length > 0 && (
          <div>
            <div className="mb-1 flex items-center justify-between gap-2">
              <label className="block text-xs text-muted-foreground">
                Speaker
              </label>
              <button
                type="button"
                onClick={loadFilters}
                className="text-xs text-muted-foreground hover:text-foreground"
              >
                Refresh
              </button>
            </div>
            <select
              value={speaker}
              onChange={(e) => setSpeaker(e.target.value)}
              className="w-full rounded-md border border-input bg-background px-2 py-1.5 text-sm"
            >
              <option value="">All speakers</option>
              {filters.speakers.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>

            {/* Speaker tabs */}
            <div className="mt-2 max-w-[520px] overflow-x-auto">
              <div className="flex gap-1.5 pb-1">
                <button
                  type="button"
                  onClick={() => setSpeaker("")}
                  className={`whitespace-nowrap rounded-full border px-2.5 py-1 text-xs ${
                    speaker === ""
                      ? "border-primary bg-primary/10 text-primary"
                      : "border-border text-muted-foreground hover:text-foreground"
                  }`}
                >
                  All
                </button>
                {filters.speakers.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => setSpeaker(s)}
                    className={`whitespace-nowrap rounded-full border px-2.5 py-1 text-xs ${
                      speaker === s
                        ? "border-primary bg-primary/10 text-primary"
                        : "border-border text-muted-foreground hover:text-foreground"
                    }`}
                    title={s}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {filters.themes.length > 0 && (
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">
              Theme
            </label>
            <select
              value={theme}
              onChange={(e) => setTheme(e.target.value)}
              className="rounded-md border border-input bg-background px-2 py-1.5 text-sm"
            >
              <option value="">All themes</option>
              {filters.themes.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>
        )}

        <div>
          <label className="mb-1 block text-xs text-muted-foreground">
            From
          </label>
          <input
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            className="rounded-md border border-input bg-background px-2 py-1.5 text-sm"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs text-muted-foreground">
            To
          </label>
          <input
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            className="rounded-md border border-input bg-background px-2 py-1.5 text-sm"
          />
        </div>
      </div>

      {/* Results */}
      {searched && (
        <div className="mt-6 space-y-4">
          <div className="text-sm text-muted-foreground">
            {loading
              ? "Searching…"
              : `${totalMentions} mention${totalMentions !== 1 ? "s" : ""} across ${totalTranscripts} transcript${totalTranscripts !== 1 ? "s" : ""}`}
          </div>

          {results.map((r) => {
            const isExpanded = expandedIds.has(r.transcript.id);
            const shownSegments = isExpanded
              ? r.segments
              : r.segments.slice(0, 2);

            return (
              <div
                key={r.transcript.id}
                className="rounded-lg border border-border bg-card"
              >
                {/* Transcript header */}
                <div className="border-b border-border px-4 py-3">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <h3 className="font-semibold">{r.transcript.title}</h3>
                      <div className="mt-0.5 flex flex-wrap gap-2 text-xs text-muted-foreground">
                        <span>
                          {new Date(r.transcript.event_date).toLocaleDateString()}
                        </span>
                        <span>{r.transcript.primary_speaker}</span>
                        <span>{r.transcript.speech_type}</span>
                        {r.transcript.total_speech_length_seconds && (
                          <span>
                            {secondsToTime(
                              r.transcript.total_speech_length_seconds
                            )}
                          </span>
                        )}
                      </div>
                    </div>
                    <span className="whitespace-nowrap rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-semibold text-primary">
                      {r.mentionCount} mention
                      {r.mentionCount !== 1 ? "s" : ""}
                    </span>
                  </div>
                </div>

                {/* Matching segments */}
                <div className="divide-y divide-border">
                  {shownSegments.map((seg, i) => (
                    <div key={i} className={`px-4 py-2.5 text-sm ${!seg.isPrimary ? "opacity-75" : ""}`}>
                      <div className="mb-0.5 flex items-center gap-2">
                        <span className={`font-medium ${seg.isPrimary ? "text-blue-400" : "text-orange-400"}`}>
                          {seg.speaker}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {secondsToTime(seg.start_seconds)}
                        </span>
                        {!seg.isPrimary && (
                          <span className="rounded bg-orange-500/20 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-orange-400">
                            Other speaker
                          </span>
                        )}
                      </div>
                      <p
                        className="text-foreground/80 leading-relaxed [&_mark]:rounded [&_mark]:bg-blue-500/20 [&_mark]:px-0.5 [&_mark]:text-blue-300 [&_mark.other]:bg-orange-500/20 [&_mark.other]:text-orange-300"
                        dangerouslySetInnerHTML={{ __html: seg.highlighted }}
                      />
                    </div>
                  ))}
                </div>

                {/* Expand/collapse */}
                {r.segments.length > 2 && (
                  <button
                    onClick={() => toggleExpand(r.transcript.id)}
                    className="w-full border-t border-border px-4 py-2 text-center text-xs text-muted-foreground hover:text-foreground"
                  >
                    {isExpanded
                      ? "Show less"
                      : `Show ${r.segments.length - 2} more matching segment${r.segments.length - 2 > 1 ? "s" : ""}`}
                  </button>
                )}
              </div>
            );
          })}

          {!loading && searched && results.length === 0 && (
            <div className="rounded-lg border border-dashed border-border p-8 text-center text-muted-foreground">
              No results found for &ldquo;{query}&rdquo;.
            </div>
          )}
        </div>
      )}
    </div>
    </div>
  );
}

