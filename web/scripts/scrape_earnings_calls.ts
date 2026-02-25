/**
 * Earnings call transcript scraper
 *
 * Primary source:  Motley Fool (monthly sitemaps → free HTML pages, back to 2020)
 * Fallback source: InsiderMonkey (WordPress REST API, no auth required)
 *
 * Usage:
 *   npm run earnings:scrape -- --tickers=NVDA,HD --dry-run=true
 *   npm run earnings:scrape -- --tickers-file=scripts/earnings_tickers_initial.txt
 *   npm run earnings:scrape -- --tickers=NVDA --min-fiscal-year=2022 --min-fiscal-quarter=1
 */

import { PrismaClient } from "@prisma/client";
import * as cheerio from "cheerio";
import type { AnyNode } from "domhandler";
import pLimit from "p-limit";
import {
  writeFileSync,
  appendFileSync,
  mkdirSync,
  existsSync,
  readFileSync,
} from "node:fs";
import { resolve } from "node:path";

const prisma = new PrismaClient();

// ─── Types ───────────────────────────────────────────────────────────────────

type Fiscal = { fiscal_year: number | null; fiscal_quarter: number | null };

type TranscriptRecord = {
  ticker: string;
  title: string;
  event_date: Date;
  fiscal: Fiscal;
  earnings_key: string | null;
  source: "motleyfool" | "insidermonkey";
  source_url: string;
  participants: { ceo?: string; cfo?: string; others: string[]; companyNames: string[] };
  segments: { speaker: string; text: string }[];
};

type RunOptions = {
  tickers: string[];
  minFiscalYear: number;
  minFiscalQuarter: number;
  dryRun: boolean;
  concurrency: number;
  delayMs: number;
  outDir: string;
  apiUrl: string | null;   // if set, POST to admin API instead of using Prisma
  apiPassword: string | null;
};

// ─── CLI args ─────────────────────────────────────────────────────────────────

function parseArgs(argv: string[]): RunOptions {
  const sp = new URLSearchParams();
  for (const a of argv) {
    const m = a.match(/^--([^=]+)=(.*)$/);
    if (m) sp.set(m[1], m[2]);
    else if (a.startsWith("--")) sp.set(a.slice(2), "true");
  }

  const tickersRaw = sp.get("tickers") ?? "";
  const fromArg = tickersRaw
    .split(",")
    .map((t) => t.trim().toUpperCase())
    .filter(Boolean);

  const tickersFile = sp.get("tickers-file");
  const fromFile = tickersFile
    ? readFileSync(tickersFile, "utf8")
        .split(/\r?\n/)
        .map((l) => l.trim())
        .filter((l) => l && !l.startsWith("#"))
        .map((l) => l.toUpperCase())
    : [];

  const tickers = Array.from(new Set([...fromArg, ...fromFile]));
  if (!tickers.length) {
    throw new Error("Missing --tickers=HD,NVDA,... or --tickers-file=path");
  }

  return {
    tickers,
    minFiscalYear: Number(sp.get("min-fiscal-year") ?? "2020"),
    minFiscalQuarter: Number(sp.get("min-fiscal-quarter") ?? "1"),
    dryRun: (sp.get("dry-run") ?? "false") === "true",
    concurrency: Math.max(1, Math.min(4, Number(sp.get("concurrency") ?? "2"))),
    delayMs: Math.max(0, Number(sp.get("delay-ms") ?? "600")),
    outDir: sp.get("out-dir") ?? "tmp/earnings_scrape",
    apiUrl: sp.get("api-url") ?? null,
    apiPassword: sp.get("api-password") ?? null,
  };
}

// ─── Utilities ────────────────────────────────────────────────────────────────

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

function norm(s: string) {
  return s.replace(/\s+/g, " ").trim();
}

function ensureDir(p: string) {
  if (!existsSync(p)) mkdirSync(p, { recursive: true });
}

function logJsonl(path: string, obj: unknown) {
  appendFileSync(path, JSON.stringify(obj) + "\n", "utf8");
}

function computeEarningsKey(ticker: string, f: Fiscal): string | null {
  if (!ticker || !f.fiscal_year || !f.fiscal_quarter) return null;
  return `${ticker.toUpperCase()}:FY${f.fiscal_year}:Q${f.fiscal_quarter}`;
}

// Derive fiscal year/quarter from a Motley Fool or InsiderMonkey transcript URL.
// Examples:
//   /nvidia-nvda-q3-2026-earnings-call-transcript/
//   /nvidia-corp-nvda-q4-2020-earnings-call-transcript.aspx
//   /nvidia-corporation-nasdaqnvda-q2-2026-earnings-call-transcript-1599650/
function parseFiscalFromUrl(url: string): Fiscal {
  const m = url.match(/-q([1-4])-(\d{4})-earnings/i);
  if (m) return { fiscal_quarter: Number(m[1]), fiscal_year: Number(m[2]) };
  return { fiscal_quarter: null, fiscal_year: null };
}

function parseFiscalFromTitle(title: string): Fiscal {
  let m = title.toUpperCase().match(/\bQ([1-4])\s+FY\s*(\d{4})\b/);
  if (m) return { fiscal_quarter: Number(m[1]), fiscal_year: Number(m[2]) };
  m = title.toUpperCase().match(/\bQ([1-4])\s+(\d{4})\b/);
  if (m) return { fiscal_quarter: Number(m[1]), fiscal_year: Number(m[2]) };
  return { fiscal_quarter: null, fiscal_year: null };
}

function isBelowMinFiscal(f: Fiscal, minYear: number, minQ: number): boolean {
  if (!f.fiscal_year || !f.fiscal_quarter) return false;
  if (f.fiscal_year < minYear) return true;
  if (f.fiscal_year > minYear) return false;
  return f.fiscal_quarter < minQ;
}

// ─── Fetching ─────────────────────────────────────────────────────────────────

const HEADERS = {
  "user-agent": "Mozilla/5.0",
  "accept-language": "en-US,en;q=0.9",
  accept: "text/html",
};

async function fetchHtml(url: string): Promise<string> {
  const res = await fetch(url, { headers: HEADERS });
  if (!res.ok) throw new Error(`HTTP ${res.status} for ${url}`);
  return res.text();
}

async function fetchJson(url: string): Promise<unknown> {
  const res = await fetch(url, {
    headers: { ...HEADERS, accept: "application/json" },
    signal: AbortSignal.timeout(25_000),
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`HTTP ${res.status} for ${url}: ${text.slice(0, 120)}`);
  return JSON.parse(text);
}

// ─── Segment parsing ──────────────────────────────────────────────────────────

/**
 * Parse speaker segments from an array of <p> DOM elements.
 * Each paragraph either starts a new speaker (has a <strong>Name:</strong> label)
 * or continues the previous speaker.
 */
function parseSegmentsFromParagraphs(
  $: cheerio.CheerioAPI,
  paragraphs: AnyNode[]
): { speaker: string; text: string }[] {
  const segments: { speaker: string; text: string }[] = [];

  const push = (speaker: string, text: string) => {
    const s = norm(speaker);
    const t = norm(text);
    if (!s || !t) return;
    const last = segments[segments.length - 1];
    if (last && last.speaker.toLowerCase() === s.toLowerCase()) {
      last.text = norm(last.text + " " + t);
      return;
    }
    segments.push({ speaker: s, text: t });
  };

  for (const p of paragraphs) {
    const full = norm($(p).text());
    if (!full) continue;

    const strong = $(p).find("strong").first();
    if (strong.length) {
      const label = norm(strong.text()).replace(/:$/, "");
      let rest = full;
      // Strip the label + optional colon from the start of the full text
      for (const candidate of [label + ":", label]) {
        if (rest.toLowerCase().startsWith(candidate.toLowerCase())) {
          rest = norm(rest.slice(candidate.length).replace(/^:\s*/, ""));
          break;
        }
      }
      if (label) { push(label, rest || full); continue; }
    }

    // Fallback: "Speaker Name: text…"
    const m = full.match(/^([^:]{2,80}):\s*(.+)$/);
    if (m) { push(m[1], m[2]); continue; }

    // Continuation
    const last = segments[segments.length - 1];
    if (last) last.text = norm(last.text + " " + full);
  }

  return segments.filter((s) => s.text.length > 0);
}

/**
 * Extract ONLY company representatives from the "Call participants" <ul>.
 * On Motley Fool the format is:
 *   <h2 id="call-participants">Call participants</h2>
 *   <ul>
 *     <li>President and CEO — Jensen Huang</li>
 *     <li>CFO — Colette Kress</li>
 *   </ul>
 * Analysts are NOT listed here — they only appear as Q&A speakers in the
 * transcript body.  Storing only company reps in `speakers_present` lets the
 * search engine distinguish company voices from external callers.
 *
 * For InsiderMonkey pages we fall back to scanning the raw text block between
 * "Call participants" and "Full Conference Call Transcript".
 */
function extractParticipants(
  $: cheerio.CheerioAPI
): { ceo?: string; cfo?: string; others: string[]; companyNames: string[] } {
  let ceo: string | undefined;
  let cfo: string | undefined;
  const others: string[] = [];
  const companyNames: string[] = [];

  // ── Strategy 1: Motley Fool <ul> under "Call participants" heading ──────────
  const h2 = $("h2, h3")
    .filter((_, el) => /call participants/i.test($(el).text()))
    .first();
  const ul = h2.next("ul");

  if (ul.length) {
    ul.find("li").each((_, li) => {
      const raw = norm($(li).text());
      // Format: "Title — Name" OR "Name — Title" (separator is em-dash)
      const parts = raw.split(/[—–]/).map((p) => norm(p)).filter(Boolean);
      if (parts.length < 2) return;
      // Heuristic: the name is the part WITHOUT a job title keyword
      const titleKeywords = /\b(officer|president|director|head|vice|investor|relations|ceo|cfo|coo|cto|controller|treasurer|secretary|analyst)\b/i;
      const nameIdx = parts.findIndex((p) => !titleKeywords.test(p));
      const name = parts[nameIdx >= 0 ? nameIdx : parts.length - 1];
      if (!name || name.length < 2) return;

      companyNames.push(name);
      const lower = raw.toLowerCase();
      if (!ceo && lower.includes("chief executive officer")) ceo = name;
      else if (!cfo && lower.includes("chief financial officer")) cfo = name;
      else others.push(name);
    });
  }

  // ── Strategy 2: text fallback (InsiderMonkey / older pages) ────────────────
  if (companyNames.length === 0) {
    const text = $.text();
    const m = text.match(/Call participants([\s\S]*?)(?:Full Conference Call Transcript|Prepared Remarks)/i);
    const block = m ? m[1] : "";
    const lines = block.split("\n").map((l) => norm(l)).filter(Boolean);

    let inAnalysts = false;
    for (const ln of lines) {
      if (/\banalysts?\b/i.test(ln) && ln.length < 30) { inAnalysts = true; continue; }
      if (inAnalysts) continue; // skip analyst names
      const name = (ln.match(/[—–-]\s*(.+)$/) || [])[1]?.trim();
      if (!name || name.length < 2) continue;
      companyNames.push(name);
      const lower = ln.toLowerCase();
      if (!ceo && lower.includes("chief executive officer")) ceo = name;
      else if (!cfo && lower.includes("chief financial officer")) cfo = name;
      else others.push(name);
    }
  }

  return { ceo, cfo, others, companyNames };
}

// ─── Motley Fool ──────────────────────────────────────────────────────────────

/** Cache of monthly sitemap URL arrays. */
const sitemapCache = new Map<string, string[]>();

async function getMotleySitemapUrls(year: number, month: number): Promise<string[]> {
  const key = `${year}-${String(month).padStart(2, "0")}`;
  if (sitemapCache.has(key)) return sitemapCache.get(key)!;
  const url = `https://www.fool.com/sitemap/${year}/${String(month).padStart(2, "0")}`;
  const res = await fetch(url, {
    headers: { "user-agent": "Mozilla/5.0", accept: "text/xml,*/*;q=0.8" },
  });
  if (!res.ok) { sitemapCache.set(key, []); return []; }
  const xml = await res.text();
  const $ = cheerio.load(xml, { xmlMode: true });
  const locs = $("url > loc").toArray().map((el) => $(el).text()).filter(Boolean);
  sitemapCache.set(key, locs);
  return locs;
}

/** Find all Motley Fool transcript URLs for a given ticker across all months since 2020. */
async function findMotleyFoolUrlsForTicker(
  ticker: string,
  minYear: number
): Promise<string[]> {
  const token = `-${ticker.toLowerCase()}-`;
  const found: string[] = [];

  const now = new Date();
  for (let y = minYear; y <= now.getFullYear(); y++) {
    const maxMonth = y === now.getFullYear() ? now.getMonth() + 1 : 12;
    for (let m = 1; m <= maxMonth; m++) {
      const urls = await getMotleySitemapUrls(y, m);
      for (const u of urls) {
        if (!u.includes("/earnings/call-transcripts/")) continue;
        if (u.toLowerCase().includes(token)) found.push(u);
      }
    }
  }

  return found;
}

/** Parse a Motley Fool transcript page into segments. */
async function parseMotleyFoolPage(
  url: string,
  ticker: string
): Promise<Omit<TranscriptRecord, "earnings_key" | "ticker">> {
  const html = await fetchHtml(url);
  const $ = cheerio.load(html);

  const title = norm(
    $("h1").first().text() ||
    $("meta[property='og:title']").attr("content") ||
    ""
  );

  // Event date from ld+json
  let event_date: Date | null = null;
  $("script[type='application/ld+json']").each((_, el) => {
    if (event_date) return;
    try {
      const j = JSON.parse($(el).text());
      const d = j?.datePublished || j?.dateModified;
      if (d) { const nd = new Date(d); if (!isNaN(nd.getTime())) event_date = nd; }
    } catch { /* skip */ }
  });
  if (!event_date) {
    // Fallback: parse from URL
    const m = url.match(/\/(\d{4})\/(\d{2})\/(\d{2})\//);
    if (m) event_date = new Date(`${m[1]}-${m[2]}-${m[3]}T00:00:00Z`);
  }
  if (!event_date || isNaN(event_date.getTime())) {
    throw new Error(`Could not extract event date from ${url}`);
  }

  const fiscalFromUrl = parseFiscalFromUrl(url);
  const fiscalFromTitle = parseFiscalFromTitle(title);
  const fiscal: Fiscal = {
    fiscal_year: fiscalFromTitle.fiscal_year ?? fiscalFromUrl.fiscal_year ?? null,
    fiscal_quarter: fiscalFromTitle.fiscal_quarter ?? fiscalFromUrl.fiscal_quarter ?? null,
  };

  const participants = extractParticipants($);
  const root = $("#article-body-transcript");
  if (!root.length) throw new Error(`No #article-body-transcript in ${url}`);

  // Collect paragraphs that follow the "Full Conference Call Transcript" header
  const allNodes = root.find("h2, h3, p").toArray();
  let started = false;
  const pEls: AnyNode[] = [];
  for (const n of allNodes) {
    const t = norm($(n).text());
    if (!started) {
      if (/full conference call transcript/i.test(t)) { started = true; continue; }
    } else if (n.tagName?.toLowerCase() === "p") {
      pEls.push(n);
    }
  }

  // Fallback: if the "Full Conference Call Transcript" header wasn't found,
  // try all paragraphs (older .aspx pages may not have the heading)
  const targetParagraphs = pEls.length ? pEls : root.find("p").toArray();

  const segments = parseSegmentsFromParagraphs($, targetParagraphs);
  if (segments.length < 10) {
    throw new Error(`Too few segments (${segments.length}) from ${url}`);
  }

  return {
    title: title || `${ticker} Earnings Call`,
    event_date,
    fiscal,
    source: "motleyfool",
    source_url: url,
    participants,
    segments,
  };
}

// ─── InsiderMonkey fallback ───────────────────────────────────────────────────

const IM_API = "https://www.insidermonkey.com/blog/wp-json/wp/v2";
const IM_CATEGORY = 271868; // "Transcripts"

/**
 * Search InsiderMonkey's WordPress REST API for a transcript by ticker/quarter.
 * Returns the post URL if found, otherwise null.
 */
async function findInsiderMonkeyUrl(args: {
  ticker: string;
  fiscal: Fiscal;
  event_date: Date;
}): Promise<string | null> {
  if (!args.fiscal.fiscal_year || !args.fiscal.fiscal_quarter) return null;

  const q = `Q${args.fiscal.fiscal_quarter} ${args.fiscal.fiscal_year} Earnings Call Transcript`;
  // Try each exchange prefix since we don't know which one InsiderMonkey used
  for (const ex of ["NASDAQ", "NYSE", "AMEX", "BATS"]) {
    const query = `(${ex}:${args.ticker.toUpperCase()}) ${q}`;
    const after = new Date(args.event_date.getTime() - 60 * 24 * 3600 * 1000).toISOString();
    const before = new Date(args.event_date.getTime() + 60 * 24 * 3600 * 1000).toISOString();
    const url =
      `${IM_API}/posts?` +
      new URLSearchParams({
        categories: String(IM_CATEGORY),
        search: query,
        after,
        before,
        per_page: "5",
        _fields: "id,link",
      });
    try {
      const j = (await fetchJson(url)) as Array<{ id: number; link: string }>;
      if (Array.isArray(j) && j.length) return j[0].link;
    } catch {
      continue;
    }
  }
  return null;
}

/** Parse an InsiderMonkey transcript HTML page into segments. */
async function parseInsiderMonkeyPage(
  url: string,
  ticker: string,
  fiscal: Fiscal,
  event_date: Date
): Promise<Omit<TranscriptRecord, "earnings_key" | "ticker">> {
  const html = await fetchHtml(url);
  const $ = cheerio.load(html);

  const title = norm($("h1").first().text() || $("meta[property='og:title']").attr("content") || "");

  const participants = extractParticipants($);

  // InsiderMonkey wraps the article in .entry-content or article.
  const article = $(".entry-content, article").first();
  const pEls = article.find("p").toArray();

  // Start parsing from first paragraph that looks like a speaker label
  let startIdx = 0;
  for (let i = 0; i < pEls.length; i++) {
    const t = norm($(pEls[i]).text());
    const strong = $(pEls[i]).find("strong").first();
    const strongText = strong.length ? norm(strong.text()) : "";
    if ((strongText && /:\s*$/.test(strongText)) || /^[^:]{2,80}:\s+\w/.test(t)) {
      startIdx = i;
      break;
    }
  }

  const segments = parseSegmentsFromParagraphs($, pEls.slice(startIdx));
  if (segments.length < 10) {
    throw new Error(`InsiderMonkey: too few segments (${segments.length}) from ${url}`);
  }

  const fiscalFromUrl = parseFiscalFromUrl(url);
  const finalFiscal: Fiscal = {
    fiscal_year: fiscal.fiscal_year ?? fiscalFromUrl.fiscal_year ?? null,
    fiscal_quarter: fiscal.fiscal_quarter ?? fiscalFromUrl.fiscal_quarter ?? null,
  };

  return {
    title: title || `${ticker} Earnings Call`,
    event_date,
    fiscal: finalFiscal,
    source: "insidermonkey",
    source_url: url,
    participants,
    segments,
  };
}

// ─── Database / API save ──────────────────────────────────────────────────────

/** Cookie jar for the admin session when using API mode. */
let _sessionCookie = "";

async function ensureApiSession(apiUrl: string, password: string) {
  if (_sessionCookie) return;
  const res = await fetch(`${apiUrl}/api/admin/auth`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ password }),
    signal: AbortSignal.timeout(15_000),
  });
  const body = await res.json() as { ok?: boolean; error?: string };
  if (!body.ok) throw new Error(`Admin login failed: ${body.error}`);
  const setCookie = res.headers.get("set-cookie") ?? "";
  const match = setCookie.match(/admin_session=([^;]+)/);
  if (!match) throw new Error("No admin_session cookie in login response");
  _sessionCookie = `admin_session=${match[1]}`;
}

async function saveViaApi(r: TranscriptRecord, apiUrl: string, password: string) {
  await ensureApiSession(apiUrl, password);

  const primary =
    r.participants.ceo ||
    r.segments.find((s) => !/operator/i.test(s.speaker))?.speaker ||
    r.ticker;

  // speakers_present = ONLY company reps (from Call participants <ul>).
  // This lets the search engine distinguish company voices from external callers.
  const speakerSet = r.participants.companyNames?.length
    ? r.participants.companyNames
    : [r.participants.ceo, r.participants.cfo, ...r.participants.others].filter(Boolean) as string[];

  const speakers_present = Array.from(
    new Map(speakerSet.map((n) => [n.toLowerCase(), n])).values()
  );

  const payload = {
    title: r.title,
    event_date: r.event_date.toISOString(),
    speech_type: "Earnings Call",
    primary_speaker: primary,
    speakers_present,
    has_q_and_a: true,
    key_themes: [],
    company_ticker: r.ticker,
    fiscal_year: r.fiscal.fiscal_year,
    fiscal_quarter: r.fiscal.fiscal_quarter,
    source: r.source,
    source_url: r.source_url,
    earnings_key: r.earnings_key,
    segments: r.segments.map((s, i) => ({
      speaker: s.speaker,
      start_seconds: i,
      end_seconds: i + 1,
      text: s.text,
    })),
  };

  const res = await fetch(`${apiUrl}/api/admin/transcripts`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      cookie: _sessionCookie,
    },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(60_000),
  });

  const body = await res.json() as { id?: string; error?: string };
  if (!res.ok || !body.id) throw new Error(`API save failed (${res.status}): ${body.error}`);
  return { transcriptId: body.id, segmentCount: r.segments.length };
}

async function upsertToDb(r: TranscriptRecord) {
  const primary =
    r.participants.ceo ||
    r.segments.find((s) => !/operator/i.test(s.speaker))?.speaker ||
    r.ticker;

  const speakers_present = Array.from(
    new Map(
      [r.participants.ceo, r.participants.cfo, ...r.participants.others, ...r.segments.map((s) => s.speaker)]
        .filter(Boolean)
        .map((n) => [n!.toLowerCase(), n!])
    ).values()
  );

  return await prisma.$transaction(async (tx) => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const where = r.earnings_key ? { earnings_key: r.earnings_key } : ({ source_url: r.source_url } as any);

    const t = await tx.transcript.upsert({
      where,
      create: {
        title: r.title,
        event_date: r.event_date,
        speech_type: "Earnings Call",
        primary_speaker: primary,
        speakers_present,
        has_q_and_a: true,
        total_speech_length_seconds: null,
        key_themes: [],
        question_count: null,
        avg_response_length_words: null,
        avg_response_length_seconds: null,
        qa_data: undefined,
        company_ticker: r.ticker,
        fiscal_year: r.fiscal.fiscal_year,
        fiscal_quarter: r.fiscal.fiscal_quarter,
        source: r.source,
        source_url: r.source_url,
        earnings_key: r.earnings_key,
      },
      update: {
        title: r.title,
        event_date: r.event_date,
        primary_speaker: primary,
        speakers_present,
        company_ticker: r.ticker,
        fiscal_year: r.fiscal.fiscal_year,
        fiscal_quarter: r.fiscal.fiscal_quarter,
        source: r.source,
        source_url: r.source_url,
        earnings_key: r.earnings_key,
      },
      select: { id: true },
    });

    await tx.speakingSegment.deleteMany({ where: { transcriptId: t.id } });

    const data = r.segments.map((s, i) => ({
      transcriptId: t.id,
      speaker: s.speaker,
      start_seconds: i,
      end_seconds: i + 1,
      text: s.text,
    }));
    for (let i = 0; i < data.length; i += 500) {
      await tx.speakingSegment.createMany({ data: data.slice(i, i + 500) });
    }

    return { transcriptId: t.id, segmentCount: r.segments.length };
  });
}

// ─── Main ─────────────────────────────────────────────────────────────────────

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  const outDir = resolve(process.cwd(), opts.outDir);
  ensureDir(outDir);

  const runId = new Date().toISOString().replace(/[:.]/g, "-");
  const logPath = resolve(outDir, `earnings-${runId}.jsonl`);
  writeFileSync(logPath, "", "utf8");

  console.error(`Run ${runId} | tickers: ${opts.tickers.join(",")} | dry-run: ${opts.dryRun}`);

  const limit = pLimit(opts.concurrency);

  for (const ticker of opts.tickers) {
    logJsonl(logPath, { type: "ticker_start", ticker, at: new Date().toISOString() });
    console.error(`\n[${ticker}] Scanning Motley Fool sitemaps…`);

    let foolUrls: string[] = [];
    try {
      foolUrls = await findMotleyFoolUrlsForTicker(ticker, opts.minFiscalYear);
      logJsonl(logPath, {
        type: "discover_ok",
        ticker,
        provider: "motleyfool",
        count: foolUrls.length,
        at: new Date().toISOString(),
      });
      console.error(`[${ticker}] Found ${foolUrls.length} Motley Fool URLs`);
    } catch (err) {
      logJsonl(logPath, {
        type: "discover_error",
        ticker,
        error: err instanceof Error ? err.message : String(err),
        at: new Date().toISOString(),
      });
      continue;
    }

    // Determine which fiscal quarters we found so we can detect gaps for InsiderMonkey
    const foundKeys = new Set<string>();

    const jobs = foolUrls.map((url) =>
      limit(async () => {
        await sleep(opts.delayMs);
        try {
          const parsed = await parseMotleyFoolPage(url, ticker);
          const earningsKey = computeEarningsKey(ticker, parsed.fiscal);
          if (earningsKey) foundKeys.add(earningsKey);

          if (isBelowMinFiscal(parsed.fiscal, opts.minFiscalYear, opts.minFiscalQuarter)) {
            return;
          }

          const record: TranscriptRecord = { ticker, earnings_key: earningsKey, ...parsed };

          if (opts.dryRun) {
            logJsonl(logPath, {
              type: "parsed_dry_run",
              ticker,
              source: "motleyfool",
              source_url: url,
              earnings_key: earningsKey,
              title: parsed.title,
              event_date: parsed.event_date.toISOString(),
              fiscal: parsed.fiscal,
              segmentCount: parsed.segments.length,
              at: new Date().toISOString(),
            });
            console.error(`  [dry-run] ${earningsKey} — ${parsed.segments.length} segments`);
            return;
          }

          const up = opts.apiUrl
            ? await saveViaApi(record, opts.apiUrl, opts.apiPassword!)
            : await upsertToDb(record);
          logJsonl(logPath, {
            type: "upsert_ok",
            ticker,
            source: "motleyfool",
            source_url: url,
            earnings_key: earningsKey,
            title: parsed.title,
            transcriptId: up.transcriptId,
            segmentCount: up.segmentCount,
            at: new Date().toISOString(),
          });
          console.error(`  [ok] ${earningsKey} — ${up.segmentCount} segments`);
        } catch (err) {
          logJsonl(logPath, {
            type: "item_error",
            ticker,
            source: "motleyfool",
            source_url: url,
            error: err instanceof Error ? err.message : String(err),
            at: new Date().toISOString(),
          });
          console.error(`  [err] ${url} — ${err instanceof Error ? err.message : err}`);
        }
      })
    );

    await Promise.all(jobs);

    // ── InsiderMonkey fallback for quarters that Motley Fool doesn't have ─────
    // Work out the expected fiscal year range from what Motley Fool returned,
    // bounded by minFiscalYear and the current calendar year + 1.
    // We use a ±1 year window around what MF found to avoid false positives.
    const now = new Date();
    const currentCalYear = now.getFullYear();

    // Derive the min/max fiscal years actually found on Motley Fool
    let mfMinFY = currentCalYear;
    let mfMaxFY = opts.minFiscalYear;
    for (const k of foundKeys) {
      const m = k.match(/:FY(\d{4}):/);
      if (m) {
        const fy = Number(m[1]);
        if (fy < mfMinFY) mfMinFY = fy;
        if (fy > mfMaxFY) mfMaxFY = fy;
      }
    }
    // Use opts.minFiscalYear as the floor
    const gapScanMinFY = Math.max(opts.minFiscalYear, mfMinFY);
    // Only look for gaps up to 1 fiscal year beyond what MF found
    const gapScanMaxFY = Math.max(mfMaxFY, currentCalYear) + 1;

    const expectedKeys: { key: string; fiscal: Fiscal; event_date: Date }[] = [];
    for (let fy = gapScanMinFY; fy <= gapScanMaxFY; fy++) {
      for (let fq = 1; fq <= 4; fq++) {
        const key = computeEarningsKey(ticker, { fiscal_year: fy, fiscal_quarter: fq });
        if (!key) continue;
        if (isBelowMinFiscal({ fiscal_year: fy, fiscal_quarter: fq }, opts.minFiscalYear, opts.minFiscalQuarter)) continue;
        // Rough event date: fiscal year runs ~Feb/May/Aug/Nov of the calendar year before.
        // This is a rough heuristic used only to bound the InsiderMonkey date search window.
        const monthMap: Record<number, number> = { 1: 2, 2: 5, 3: 8, 4: 11 };
        const eventDate = new Date(Date.UTC(fy - 1, (monthMap[fq] ?? 2) - 1, 15));
        // Skip if event date is more than 3 months in the future (unlikely to exist yet)
        if (eventDate.getTime() > now.getTime() + 90 * 24 * 3600 * 1000) continue;
        // Skip if found via Motley Fool
        if (foundKeys.has(key)) continue;
        expectedKeys.push({ key, fiscal: { fiscal_year: fy, fiscal_quarter: fq }, event_date: eventDate });
      }
    }

    if (expectedKeys.length > 0) {
      console.error(`[${ticker}] ${expectedKeys.length} quarter(s) not found on Motley Fool — trying InsiderMonkey…`);
    }

    for (const { key, fiscal, event_date } of expectedKeys) {
      await sleep(opts.delayMs);
      logJsonl(logPath, {
        type: "motleyfool_gap",
        ticker,
        earnings_key: key,
        at: new Date().toISOString(),
      });

      try {
        const imUrl = await findInsiderMonkeyUrl({ ticker, fiscal, event_date });
        if (!imUrl) {
          logJsonl(logPath, {
            type: "not_found",
            ticker,
            earnings_key: key,
            at: new Date().toISOString(),
          });
          console.error(`  [not found] ${key}`);
          continue;
        }

        const parsed = await parseInsiderMonkeyPage(imUrl, ticker, fiscal, event_date);
        const earningsKey = computeEarningsKey(ticker, parsed.fiscal);
        const record: TranscriptRecord = { ticker, earnings_key: earningsKey, ...parsed };

        if (opts.dryRun) {
          logJsonl(logPath, {
            type: "parsed_dry_run",
            ticker,
            source: "insidermonkey",
            source_url: imUrl,
            earnings_key: earningsKey,
            title: parsed.title,
            event_date: parsed.event_date.toISOString(),
            fiscal: parsed.fiscal,
            segmentCount: parsed.segments.length,
            at: new Date().toISOString(),
          });
          console.error(`  [dry-run IM] ${earningsKey} — ${parsed.segments.length} segments`);
        } else {
          const up = opts.apiUrl
            ? await saveViaApi(record, opts.apiUrl, opts.apiPassword!)
            : await upsertToDb(record);
          logJsonl(logPath, {
            type: "upsert_ok",
            ticker,
            source: "insidermonkey",
            source_url: imUrl,
            earnings_key: earningsKey,
            title: parsed.title,
            transcriptId: up.transcriptId,
            segmentCount: up.segmentCount,
            at: new Date().toISOString(),
          });
          console.error(`  [ok IM] ${earningsKey} — ${up.segmentCount} segments`);
        }
      } catch (err) {
        logJsonl(logPath, {
          type: "fallback_error",
          ticker,
          earnings_key: key,
          provider: "insidermonkey",
          error: err instanceof Error ? err.message : String(err),
          at: new Date().toISOString(),
        });
        console.error(`  [IM err] ${key} — ${err instanceof Error ? err.message : err}`);
      }
    }

    logJsonl(logPath, { type: "ticker_done", ticker, at: new Date().toISOString() });
  }

  logJsonl(logPath, { type: "run_done", at: new Date().toISOString() });
  console.error("\nDone. Log:", logPath);
  if (!opts.apiUrl) await prisma.$disconnect();
}

main().catch((e) => { console.error(e); process.exit(1); });
