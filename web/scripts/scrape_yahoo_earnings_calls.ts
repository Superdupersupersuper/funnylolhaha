import { PrismaClient } from "@prisma/client";
import * as cheerio from "cheerio";
import pLimit from "p-limit";
import { Agent } from "undici";
import {
  writeFileSync,
  appendFileSync,
  mkdirSync,
  existsSync,
  readFileSync,
} from "node:fs";
import { resolve } from "node:path";

const prisma = new PrismaClient({
  log: process.env.NODE_ENV === "development" ? ["query"] : [],
});

// Yahoo (and its consent redirects) can return large header blocks (esp. many Set-Cookie values).
// Increase the max header size so Node's fetch (undici) doesn't error.
const dispatcher = new Agent({ maxHeaderSize: 64 * 1024 });

type Fiscal = { fiscal_year: number | null; fiscal_quarter: number | null };

type DiscoveredItem = {
  ticker: string;
  titleHint?: string;
  fiscal_year?: number | null;
  fiscal_quarter?: number | null;
  transcriptId?: number | null;
  event_epoch_seconds?: number | null;
  source_url: string;
};

type ParsedEarningsCall = {
  ticker: string;
  title: string;
  event_date: Date;
  fiscal: Fiscal;
  earnings_key: string | null;
  source_url: string;
  source: "yahoo" | "motleyfool" | "insidermonkey";
  participants: {
    ceo?: string;
    cfo?: string;
    others: string[];
  };
  segments: { speaker: string; text: string }[];
};

type RunOptions = {
  tickers: string[];
  tickersFile: string | null;
  minFiscalYear: number;
  minFiscalQuarter: number;
  dryRun: boolean;
  requireComplete: boolean;
  concurrency: number;
  delayMs: number;
  outDir: string;
};

function parseArgs(argv: string[]): RunOptions {
  const sp = new URLSearchParams();
  for (const a of argv) {
    const m = a.match(/^--([^=]+)=(.*)$/);
    if (m) sp.set(m[1], m[2]);
    else if (a.startsWith("--")) sp.set(a.slice(2), "true");
  }

  const tickersRaw = sp.get("tickers") ?? "";
  const tickersFromArgv =
    tickersRaw
      .split(",")
      .map((t) => t.trim().toUpperCase())
      .filter(Boolean) ?? [];

  const tickersFile = sp.get("tickers-file");
  const tickersFromFile = tickersFile
    ? readFileSync(tickersFile, "utf8")
        .split(/\r?\n/)
        .map((l) => l.trim())
        .filter((l) => l && !l.startsWith("#"))
        .map((l) => l.toUpperCase())
    : [];

  const tickers = Array.from(new Set([...tickersFromArgv, ...tickersFromFile]));

  const minFiscalYear = Number(sp.get("min-fiscal-year") ?? "2020");
  const minFiscalQuarter = Number(sp.get("min-fiscal-quarter") ?? "1");

  const dryRun = (sp.get("dry-run") ?? "false") === "true";
  const requireComplete = (sp.get("require-complete") ?? "true") === "true";
  const concurrency = Math.max(1, Math.min(6, Number(sp.get("concurrency") ?? "2")));
  const delayMs = Math.max(0, Number(sp.get("delay-ms") ?? "800"));
  const outDir = sp.get("out-dir") ?? "tmp/earnings_scrape";

  if (!tickers.length) {
    throw new Error("Missing --tickers=HD,NVDA,... or --tickers-file=path.txt");
  }
  if (!Number.isFinite(minFiscalYear) || minFiscalYear < 1900) {
    throw new Error("Invalid --min-fiscal-year");
  }
  if (![1, 2, 3, 4].includes(minFiscalQuarter)) {
    throw new Error("Invalid --min-fiscal-quarter (1-4)");
  }

  return {
    tickers,
    tickersFile: tickersFile ?? null,
    minFiscalYear,
    minFiscalQuarter,
    dryRun,
    requireComplete,
    concurrency,
    delayMs,
    outDir,
  };
}

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

function nowIsoCompact() {
  return new Date().toISOString().replace(/[:.]/g, "-");
}

function ensureDir(p: string) {
  if (!existsSync(p)) mkdirSync(p, { recursive: true });
}

function logJsonl(path: string, obj: unknown) {
  appendFileSync(path, JSON.stringify(obj) + "\n", "utf8");
}

function normalizeWhitespace(s: string) {
  return s.replace(/\s+/g, " ").trim();
}

class IncompleteTranscriptError extends Error {
  meta: {
    ticker: string;
    title: string;
    event_date: Date;
    fiscal: Fiscal;
    source_url: string;
    participants: ParsedEarningsCall["participants"];
  };

  constructor(
    message: string,
    meta: {
      ticker: string;
      title: string;
      event_date: Date;
      fiscal: Fiscal;
      source_url: string;
      participants: ParsedEarningsCall["participants"];
    }
  ) {
    super(message);
    this.name = "IncompleteTranscriptError";
    this.meta = meta;
  }
}

type CookieJar = Map<string, string>;

function decodeHtmlAttr(v: string) {
  // Minimal decoding for common entities we see in Yahoo consent form hidden inputs.
  return v
    .replace(/&amp;/g, "&")
    .replace(/&#x3D;/gi, "=")
    .replace(/&#x26;/gi, "&")
    .replace(/&#x2F;/gi, "/")
    .replace(/&#x3F;/gi, "?");
}

function cookieHeader(jar: CookieJar) {
  const parts: string[] = [];
  for (const [k, v] of jar.entries()) parts.push(`${k}=${v}`);
  return parts.join("; ");
}

function ingestSetCookie(jar: CookieJar, setCookie: string) {
  const first = setCookie.split(";")[0];
  const eq = first.indexOf("=");
  if (eq <= 0) return;
  const name = first.slice(0, eq).trim();
  const value = first.slice(eq + 1).trim();
  if (!name) return;
  jar.set(name, value);
}

function getSetCookies(res: Response): string[] {
  // undici Headers in Node provides getSetCookie()
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const h: any = res.headers;
  if (typeof h.getSetCookie === "function") return h.getSetCookie();
  const one = res.headers.get("set-cookie");
  return one ? [one] : [];
}

function isYahooConsentGate(html: string) {
  const t = html.toLowerCase();
  return (
    (t.includes("consent-page") && t.includes("consent-form")) ||
    t.includes("tu privacidad es importante") ||
    t.includes("your privacy is important")
  );
}

function extractConsentForm(html: string): {
  csrfToken: string;
  sessionId: string;
  originalDoneUrl: string;
  namespace: string;
  actionUrl: string;
} | null {
  const $ = cheerio.load(html);
  const form = $("form.consent-form").first();
  if (!form.length) return null;

  const csrfToken = String(
    form.find('input[name="csrfToken"]').attr("value") ?? ""
  ).trim();
  const sessionId = String(
    form.find('input[name="sessionId"]').attr("value") ?? ""
  ).trim();
  const originalDoneUrl = decodeHtmlAttr(
    String(
    form.find('input[name="originalDoneUrl"]').attr("value") ?? ""
    ).trim()
  );
  const namespace = String(
    form.find('input[name="namespace"]').attr("value") ?? ""
  ).trim();
  const actionUrl = decodeHtmlAttr(String(form.attr("action") ?? "").trim());

  if (!csrfToken || !sessionId || !originalDoneUrl || !namespace) return null;
  return { csrfToken, sessionId, originalDoneUrl, namespace, actionUrl };
}

function acceptForUrl(url: string) {
  // Observed behavior (2026-02): transcript pages under /earnings/ require a wide Accept
  // but the earnings-calls list page is more reliable with a simple Accept.
  if (/\/quote\/[^/]+\/earnings\//i.test(url)) {
    return "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8";
  }
  return "text/html";
}

async function fetchWithCookies(
  jar: CookieJar,
  url: string,
  init: RequestInit & { redirect?: "manual" | "follow"; dispatcher?: unknown } = {}
) {
  const headers = new Headers(init.headers);
  headers.set(
    "user-agent",
    headers.get("user-agent") ?? "Mozilla/5.0"
  );
  headers.set("accept-language", headers.get("accept-language") ?? "en-US,en;q=0.9");
  headers.set(
    "accept",
    headers.get("accept") ?? acceptForUrl(url)
  );

  const cookie = cookieHeader(jar);
  if (cookie) headers.set("cookie", cookie);

  const res = await fetch(url, {
    ...init,
    headers,
    redirect: init.redirect ?? "manual",
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    dispatcher: (init as any).dispatcher ?? (dispatcher as any),
  });
  for (const sc of getSetCookies(res)) ingestSetCookie(jar, sc);
  return res;
}

function isBelowMinFiscal(f: Fiscal, minYear: number, minQ: number) {
  if (!f.fiscal_year || !f.fiscal_quarter) return false; // unknown => keep
  if (f.fiscal_year < minYear) return true;
  if (f.fiscal_year > minYear) return false;
  return f.fiscal_quarter < minQ;
}

function parseFiscalFromTitle(title: string): Fiscal {
  const t = title.toUpperCase();
  // Common: "NVDA Q3 FY2026 earnings call transcript"
  let m = t.match(/\bQ([1-4])\s+FY\s*([0-9]{4})\b/);
  if (m) return { fiscal_quarter: Number(m[1]), fiscal_year: Number(m[2]) };

  // Also seen: "Zillow (Z) Q4 2025 Earnings Call Transcript" (calendar year)
  m = t.match(/\bQ([1-4])\s+([0-9]{4})\b/);
  if (m) return { fiscal_quarter: Number(m[1]), fiscal_year: Number(m[2]) };

  return { fiscal_quarter: null, fiscal_year: null };
}

function inferFiscalFromYahooUrl(url: string): Fiscal {
  // Typical: .../NVDA-Q2-2026-earnings_call-351238.html
  const m = url.toUpperCase().match(/-Q([1-4])-([0-9]{4})-EARNINGS_CALL-/);
  if (!m) return { fiscal_year: null, fiscal_quarter: null };
  return { fiscal_quarter: Number(m[1]), fiscal_year: Number(m[2]) };
}

function computeEarningsKey(ticker: string, f: Fiscal): string | null {
  if (!ticker) return null;
  if (!f.fiscal_year || !f.fiscal_quarter) return null;
  return `${ticker.toUpperCase()}:FY${f.fiscal_year}:Q${f.fiscal_quarter}`;
}

function extractRootAppMain(html: string): unknown | null {
  // Yahoo commonly embeds a JSON blob in `root.App.main = {...};`
  // The surrounding wrapper changes frequently, so use a small brace-matching parser.
  const idx = html.indexOf("root.App.main");
  if (idx < 0) return null;
  const after = html.slice(idx);
  const eq = after.indexOf("=");
  if (eq < 0) return null;
  const start = after.indexOf("{", eq);
  if (start < 0) return null;

  let depth = 0;
  let inStr = false;
  let esc = false;
  for (let i = start; i < after.length; i++) {
    const ch = after[i];
    if (inStr) {
      if (esc) {
        esc = false;
      } else if (ch === "\\") {
        esc = true;
      } else if (ch === '"') {
        inStr = false;
      }
      continue;
    }
    if (ch === '"') {
      inStr = true;
      continue;
    }
    if (ch === "{") depth++;
    if (ch === "}") depth--;
    if (depth === 0) {
      const jsonText = after.slice(start, i + 1);
      try {
        return JSON.parse(jsonText);
      } catch {
        return null;
      }
    }
  }
  return null;
}

function collectNewsUrlsFromObject(obj: unknown, out: Set<string>) {
  if (!obj) return;
  if (typeof obj === "string") {
    if (obj.startsWith("https://finance.yahoo.com/news/")) out.add(obj);
    return;
  }
  if (Array.isArray(obj)) {
    for (const v of obj) collectNewsUrlsFromObject(v, out);
    return;
  }
  if (typeof obj === "object") {
    for (const v of Object.values(obj as Record<string, unknown>)) {
      collectNewsUrlsFromObject(v, out);
    }
  }
}

function parseFiscalPeriod(fp: unknown): number | null {
  if (typeof fp !== "string") return null;
  const m = fp.toUpperCase().match(/\bQ([1-4])\b/);
  return m ? Number(m[1]) : null;
}

function extractEmbeddedEarningsTranscripts(
  html: string,
  ticker: string
): Array<{
  title?: string;
  fiscalYear?: number;
  fiscalPeriod?: string;
  date?: number;
  url?: string;
  transcriptId?: number;
}> | null {
  const $ = cheerio.load(html);
  const scripts = $('script[type="application/json"][data-sveltekit-fetched]');
  for (const el of scripts.toArray()) {
    const rawUrl = String($(el).attr("data-url") ?? "");
    const dataUrl = decodeHtmlAttr(rawUrl);
    if (!dataUrl.includes(`/quoteSummary/${ticker}`)) continue;
    if (!dataUrl.includes("earningsCallTranscripts")) continue;

    const raw = $(el).text();
    if (!raw) continue;
    try {
      const outer = JSON.parse(raw);
      const body = JSON.parse(outer.body);
      const result = body?.quoteSummary?.result?.[0];
      const ect = result?.earningsCallTranscripts;
      const transcripts = ect?.transcripts;
      if (Array.isArray(transcripts)) return transcripts;
    } catch {
      // ignore
    }
  }
  return null;
}

async function fetchHtml(url: string, jar?: CookieJar): Promise<string> {
  // Yahoo often presents a consent gate (EU). We auto-reject and continue with a cookie jar.
  const cookieJar: CookieJar = jar ?? new Map();
  let currentUrl = url;
  const originalUrl = url;
  const trace = process.env.EARNINGS_SCRAPER_TRACE === "1";

  for (let step = 0; step < 6; step++) {
    if (trace) console.error(`[fetchHtml] GET ${currentUrl}`);
    const res = await fetchWithCookies(cookieJar, currentUrl, { method: "GET" });
    if (trace) console.error(`[fetchHtml] <- ${res.status} ${currentUrl}`);

    if (res.status >= 300 && res.status < 400) {
      const loc = res.headers.get("location");
      if (!loc) throw new Error(`Redirect ${res.status} missing Location`);
      currentUrl = new URL(loc, currentUrl).toString();
      continue;
    }

    const html = await res.text();

    if (!res.ok) {
      if (process.env.EARNINGS_SCRAPER_DEBUG === "1") {
        // Keep it short to avoid log spam.
        const sample = html.slice(0, 300).replace(/\s+/g, " ").trim();
        console.error(`[fetchHtml] status=${res.status} url=${currentUrl} body="${sample}"`);
      }
      throw new Error(`HTTP ${res.status} ${res.statusText} for ${currentUrl}`);
    }

    if (!isYahooConsentGate(html)) return html;

    const form = extractConsentForm(html);
    if (!form) throw new Error("Hit Yahoo consent gate but could not parse consent form");

    const postUrl = form.actionUrl
      ? new URL(form.actionUrl, currentUrl).toString()
      : currentUrl;
    const body = new URLSearchParams({
      csrfToken: form.csrfToken,
      sessionId: form.sessionId,
      originalDoneUrl: form.originalDoneUrl,
      namespace: form.namespace,
      reject: "reject",
    }).toString();

    if (trace) console.error(`[fetchHtml] POST ${postUrl} (reject)`);
    const postRes = await fetchWithCookies(cookieJar, postUrl, {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      body,
    });
    if (trace) console.error(`[fetchHtml] <- ${postRes.status} ${postUrl}`);

    // Follow any redirect hops after submitting consent (they sometimes set additional cookies),
    // then retry the original URL.
    let next = postRes.headers.get("location")
      ? new URL(postRes.headers.get("location")!, postUrl).toString()
      : form.originalDoneUrl;

    for (let hop = 0; hop < 4; hop++) {
      if (trace) console.error(`[fetchHtml] HOP GET ${next}`);
      const r = await fetchWithCookies(cookieJar, next, { method: "GET" });
      if (trace) console.error(`[fetchHtml] HOP <- ${r.status} ${next}`);
      if (r.status >= 300 && r.status < 400) {
        const loc = r.headers.get("location");
        if (!loc) break;
        next = new URL(loc, next).toString();
        continue;
      }
      try {
        await r.text();
      } catch {
        // ignore
      }
      break;
    }

    // After consent is processed, Yahoo's done URL (often includes guccounter=1) is the safest next fetch.
    currentUrl = form.originalDoneUrl || originalUrl;
  }

  throw new Error("Too many redirects/consent steps");
}

async function discoverForTicker(
  ticker: string
): Promise<{ items: DiscoveredItem[]; cookieSeed: CookieJar }> {
  const url = `https://finance.yahoo.com/quote/${encodeURIComponent(ticker)}/earnings-calls/`;
  const cookieSeed: CookieJar = new Map();
  const html = await fetchHtml(url, cookieSeed);

  // Prefer embedded quoteSummary JSON (includes canonical transcript URLs + fiscal info)
  const embedded = extractEmbeddedEarningsTranscripts(html, ticker);
  if (embedded && embedded.length > 0) {
    return {
      cookieSeed,
      items: embedded
        .map((t) => ({
          ticker,
          titleHint: typeof t.title === "string" ? t.title : undefined,
          fiscal_year: typeof t.fiscalYear === "number" ? t.fiscalYear : null,
          fiscal_quarter: parseFiscalPeriod(t.fiscalPeriod),
          transcriptId: typeof t.transcriptId === "number" ? t.transcriptId : null,
          event_epoch_seconds: typeof t.date === "number" ? t.date : null,
          source_url: typeof t.url === "string" ? t.url : "",
        }))
        .filter((x) => x.source_url.startsWith("http")),
    };
  }

  // Fallback 1: older pages might still include root.App.main URLs
  const urls = new Set<string>();
  const root = extractRootAppMain(html);
  if (root) collectNewsUrlsFromObject(root, urls);

  // Fallback 2: collect relevant anchor links
  const $ = cheerio.load(html);
  $("a[href]").each((_, el) => {
    const href = $(el).attr("href");
    if (!href) return;
    const abs = href.startsWith("http") ? href : `https://finance.yahoo.com${href}`;
    urls.add(abs);
  });

  const filtered = Array.from(urls).filter((u) => {
    if (!u.startsWith("https://finance.yahoo.com/")) return false;
    // canonical earnings transcript pages
    if (u.includes(`/quote/${ticker}/earnings/`) && u.includes("earnings_call")) return true;
    // older “news article” transcripts
    if (/earnings-call/i.test(u) && /transcript/i.test(u)) return true;
    return false;
  });

  return { cookieSeed, items: filtered.map((source_url) => ({ ticker, source_url })) };
}

function extractArticleTitle($: cheerio.CheerioAPI) {
  const h1 = normalizeWhitespace($("h1").first().text());
  if (h1) return h1;
  const og = $("meta[property='og:title']").attr("content");
  if (og) return normalizeWhitespace(og);
  return "";
}

function extractEventDate($: cheerio.CheerioAPI): Date | null {
  // Articles like:
  // ## Date
  // Tuesday, February 10, 2026 at 5 p.m. ET
  const text = $.text();
  const m = text.match(/\bDate\b[\s\S]{0,200}?\b([A-Z][a-z]+,\s+[A-Z][a-z]+\s+\d{1,2},\s+\d{4})\b/);
  if (m) {
    const d = new Date(m[1]);
    if (!Number.isNaN(d.getTime())) return d;
  }

  // Fallback: try ISO-ish in time tags
  const dt = $("time").attr("datetime");
  if (dt) {
    const d = new Date(dt);
    if (!Number.isNaN(d.getTime())) return d;
  }

  return null;
}

function extractParticipants($: cheerio.CheerioAPI): ParsedEarningsCall["participants"] {
  // Try to locate "Call participants" section; the plain text contains lines like:
  // Chief Executive Officer — Jeremy Wacksman
  const text = $.text();
  const sectionMatch = text.match(/Call participants([\s\S]*?)Full Conference Call Transcript/i);
  const block = sectionMatch ? sectionMatch[1] : "";
  const lines = block
    .split("\n")
    .map((l) => normalizeWhitespace(l))
    .filter(Boolean);

  let ceo: string | undefined;
  let cfo: string | undefined;
  const others: string[] = [];

  for (const ln of lines) {
    const m = ln.match(/—\s*(.+)$/);
    const name = m ? normalizeWhitespace(m[1]) : "";
    if (!name) continue;
    const lower = ln.toLowerCase();
    if (!ceo && lower.includes("chief executive officer")) ceo = name;
    else if (!cfo && lower.includes("chief financial officer")) cfo = name;
    else others.push(name);
  }

  return { ceo, cfo, others };
}

function extractTranscriptBodyText($: cheerio.CheerioAPI): string {
  // WebFetch output shows markdown; the HTML typically has all text in the article.
  // We'll take everything after "Full Conference Call Transcript" until the end,
  // but strip some boilerplate tokens.
  const full = $.text();
  const idx = full.toLowerCase().indexOf("full conference call transcript");
  const slice = idx >= 0 ? full.slice(idx) : full;
  return slice;
}

function extractEmbeddedTranscriptXhrBody(html: string): unknown | null {
  const $ = cheerio.load(html);
  const scripts = $('script[type="application/json"][data-sveltekit-fetched]');
  for (const el of scripts.toArray()) {
    const rawUrl = String($(el).attr("data-url") ?? "");
    const dataUrl = decodeHtmlAttr(rawUrl);
    if (!dataUrl.startsWith("/xhr/transcript?")) continue;
    const raw = $(el).text();
    if (!raw) continue;
    try {
      const outer = JSON.parse(raw);
      return JSON.parse(outer.body);
    } catch {
      return null;
    }
  }
  return null;
}

function parseSegmentsFromTranscriptJson(json: unknown): { speaker: string; text: string }[] {
  if (!json || typeof json !== "object") return [];
  const tc = (json as Record<string, unknown>).transcriptContent as
    | Record<string, unknown>
    | undefined;
  if (!tc) return [];

  const mappingArr = tc.speaker_mapping as unknown;
  const map = new Map<number, string>();
  if (Array.isArray(mappingArr)) {
    for (const it of mappingArr) {
      if (!it || typeof it !== "object") continue;
      const speaker = (it as Record<string, unknown>).speaker;
      const sd = (it as Record<string, unknown>).speaker_data as
        | Record<string, unknown>
        | undefined;
      const name = sd ? sd.name : undefined;
      if (typeof speaker === "number" && typeof name === "string" && name.trim()) {
        map.set(speaker, name.trim());
      }
    }
  }

  // Quartr/Yahoo payloads often provide paragraphs with speaker indices.
  const transcript = tc.transcript as unknown;
  const paragraphs =
    transcript && typeof transcript === "object"
      ? ((transcript as Record<string, unknown>).paragraphs as unknown)
      : null;

  const segArr =
    (tc.segments as unknown) ||
    (tc.transcript_segments as unknown) ||
    (tc.transcriptSegments as unknown) ||
    paragraphs;
  if (!Array.isArray(segArr)) return [];

  const segments: { speaker: string; text: string }[] = [];
  for (const s of segArr) {
    if (!s || typeof s !== "object") continue;
    const sp = (s as Record<string, unknown>).speaker;
    const txt = (s as Record<string, unknown>).text;
    if (typeof txt !== "string") continue;
    const speakerName =
      typeof sp === "number" ? map.get(sp) ?? `Speaker ${sp}` : "Unknown";
    const cleaned = normalizeWhitespace(txt);
    if (!cleaned) continue;
    segments.push({ speaker: speakerName, text: cleaned });
  }
  return segments;
}

function parseSpeakerSegments(raw: string): { speaker: string; text: string }[] {
  // We rely on "Speaker Name: text" starts. Many transcripts are like:
  // Bradley Berning: Thank you...
  const cleaned = raw
    .replace(/\r/g, "")
    .replace(/Story Continues/gi, "\n")
    .replace(/\n{3,}/g, "\n\n");

  const lines = cleaned.split("\n").map((l) => l.trim()).filter(Boolean);

  const segments: { speaker: string; text: string }[] = [];
  let curSpeaker: string | null = null;
  let curParts: string[] = [];

  const speakerRe = /^([A-Z][^:]{0,80}):\s*(.*)$/;

  function flush() {
    if (!curSpeaker) return;
    const text = normalizeWhitespace(curParts.join(" "));
    if (text && curSpeaker.toLowerCase() !== "image source") {
      segments.push({ speaker: curSpeaker, text });
    }
    curSpeaker = null;
    curParts = [];
  }

  for (const ln of lines) {
    // skip section headers/labels
    if (/^(date|call participants|full conference call transcript)$/i.test(ln)) continue;
    if (/^oops, something went wrong$/i.test(ln)) continue;
    if (/^image source:/i.test(ln)) continue;

    const m = speakerRe.exec(ln);
    if (m) {
      flush();
      curSpeaker = normalizeWhitespace(m[1]);
      const first = m[2]?.trim();
      if (first) curParts.push(first);
      continue;
    }

    if (curSpeaker) curParts.push(ln);
  }

  flush();
  return segments;
}

function parseSegmentsFromParagraphs(
  $: cheerio.CheerioAPI,
  paragraphs: cheerio.Element[]
): { speaker: string; text: string }[] {
  const segments: { speaker: string; text: string }[] = [];

  const push = (speaker: string, text: string) => {
    const s = normalizeWhitespace(speaker);
    const t = normalizeWhitespace(text);
    if (!s || !t) return;
    const last = segments[segments.length - 1];
    if (last && last.speaker.toLowerCase() === s.toLowerCase()) {
      last.text = normalizeWhitespace(`${last.text} ${t}`);
      return;
    }
    segments.push({ speaker: s, text: t });
  };

  for (const p of paragraphs) {
    const pText = normalizeWhitespace($(p).text());
    if (!pText) continue;

    const strong = $(p).find("strong").first();
    if (strong.length) {
      const strongText = normalizeWhitespace(strong.text());
      const speaker = strongText.replace(/:$/, "").trim();
      // Remove the speaker label from the full paragraph text.
      let rest = pText;
      if (strongText) {
        if (rest.toLowerCase().startsWith(strongText.toLowerCase())) {
          rest = rest.slice(strongText.length);
        } else if (rest.toLowerCase().startsWith((speaker + ":").toLowerCase())) {
          rest = rest.slice(speaker.length + 1);
        } else if (rest.toLowerCase().startsWith(speaker.toLowerCase())) {
          rest = rest.slice(speaker.length);
        }
      }
      rest = normalizeWhitespace(rest.replace(/^:\s*/, ""));
      if (speaker && rest) {
        push(speaker, rest);
        continue;
      }
    }

    const m = pText.match(/^([^:]{2,80}):\s*(.+)$/);
    if (m) {
      push(m[1], m[2]);
      continue;
    }

    // Continuation of previous speaker
    const last = segments[segments.length - 1];
    if (last) last.text = normalizeWhitespace(`${last.text} ${pText}`);
  }

  return segments;
}

const motleySitemapCache = new Map<string, string[]>();

async function fetchMotleySitemapUrls(year: number, month: number): Promise<string[]> {
  const key = `${year}-${String(month).padStart(2, "0")}`;
  const cached = motleySitemapCache.get(key);
  if (cached) return cached;

  const url = `https://www.fool.com/sitemap/${year}/${String(month).padStart(2, "0")}`;
  const res = await fetch(url, {
    headers: {
      "user-agent": "Mozilla/5.0",
      accept: "application/xml,text/xml;q=0.9,*/*;q=0.8",
      "accept-language": "en-US,en;q=0.9",
    },
  });
  if (!res.ok) throw new Error(`MotleyFool sitemap HTTP ${res.status} for ${url}`);
  const xml = await res.text();
  const $ = cheerio.load(xml, { xmlMode: true });
  const locs = $("url > loc")
    .toArray()
    .map((el) => $(el).text())
    .filter(Boolean);
  motleySitemapCache.set(key, locs);
  return locs;
}

function parseDateFromMotleyUrl(url: string): Date | null {
  const m = url.match(/\/earnings\/call-transcripts\/(\d{4})\/(\d{2})\/(\d{2})\//);
  if (!m) return null;
  const d = new Date(`${m[1]}-${m[2]}-${m[3]}T00:00:00Z`);
  return Number.isNaN(d.getTime()) ? null : d;
}

async function findMotleyFoolTranscriptUrl(args: {
  ticker: string;
  fiscal: Fiscal;
  event_date: Date;
}): Promise<string | null> {
  const { ticker, fiscal, event_date } = args;
  if (!fiscal.fiscal_year || !fiscal.fiscal_quarter) return null;

  // Try the month of the event date, plus adjacent months to handle publish-date drift.
  const monthsToTry = new Set<string>();
  for (const deltaDays of [-7, 0, 14]) {
    const d = new Date(event_date.getTime() + deltaDays * 24 * 3600 * 1000);
    monthsToTry.add(`${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`);
  }

  const desired = `q${fiscal.fiscal_quarter}-${fiscal.fiscal_year}`.toLowerCase();
  const token = `-${ticker.toLowerCase()}-`;

  const candidates: string[] = [];
  for (const ym of Array.from(monthsToTry)) {
    const [y, m] = ym.split("-").map(Number);
    const urls = await fetchMotleySitemapUrls(y, m);
    for (const u of urls) {
      if (!u.includes("/earnings/call-transcripts/")) continue;
      const lower = u.toLowerCase();
      if (!lower.includes(token)) continue;
      if (!lower.includes(desired)) continue;
      candidates.push(u);
    }
  }

  if (!candidates.length) return null;

  // Pick closest URL date to the event_date
  candidates.sort((a, b) => {
    const da = parseDateFromMotleyUrl(a)?.getTime() ?? 0;
    const db = parseDateFromMotleyUrl(b)?.getTime() ?? 0;
    const ta = Math.abs(da - event_date.getTime());
    const tb = Math.abs(db - event_date.getTime());
    return ta - tb;
  });
  return candidates[0] ?? null;
}

async function parseMotleyFoolTranscript(args: {
  ticker: string;
  fiscal: Fiscal;
  event_date: Date;
  url: string;
}): Promise<Pick<ParsedEarningsCall, "title" | "participants" | "segments">> {
  const res = await fetch(args.url, {
    headers: {
      "user-agent": "Mozilla/5.0",
      accept: "text/html",
      "accept-language": "en-US,en;q=0.9",
    },
  });
  if (!res.ok) throw new Error(`MotleyFool transcript HTTP ${res.status} for ${args.url}`);
  const html = await res.text();
  const $ = cheerio.load(html);
  const title = extractArticleTitle($) || "Motley Fool";
  const participants = extractParticipants($);

  const root = $("#article-body-transcript");
  if (!root.length) throw new Error("MotleyFool transcript missing #article-body-transcript");

  const nodes = root.find("h2, h3, p").toArray();
  let started = false;
  const pEls: cheerio.Element[] = [];
  for (const n of nodes) {
    const t = normalizeWhitespace($(n).text());
    if (!started) {
      if (/full conference call transcript/i.test(t)) started = true;
      continue;
    }
    if (n.tagName?.toLowerCase() === "p") pEls.push(n);
  }

  const segments = parseSegmentsFromParagraphs($, pEls);
  if (segments.length < 10) {
    throw new Error(`MotleyFool: too few speaker segments (${segments.length})`);
  }

  return { title, participants, segments };
}

const INSIDERMONKEY_API_BASE = "https://www.insidermonkey.com/blog/wp-json/wp/v2";
const INSIDERMONKEY_TRANSCRIPTS_CATEGORY_ID = 271868;

type InsiderMonkeySearchHit = {
  id: number;
  link: string;
  slug: string;
  date: string;
  title: { rendered: string };
};

async function fetchInsiderMonkeyJson(url: string) {
  const res = await fetch(url, {
    headers: {
      "user-agent": "Mozilla/5.0",
      accept: "application/json",
      "accept-language": "en-US,en;q=0.9",
    },
  });
  const text = await res.text();
  if (!res.ok) {
    const sample = text.slice(0, 200).replace(/\s+/g, " ").trim();
    throw new Error(`InsiderMonkey HTTP ${res.status} for ${url} body="${sample}"`);
  }
  try {
    return JSON.parse(text) as unknown;
  } catch {
    const sample = text.slice(0, 200).replace(/\s+/g, " ").trim();
    throw new Error(`InsiderMonkey non-JSON response for ${url} body="${sample}"`);
  }
}

async function findInsiderMonkeyTranscriptPost(args: {
  ticker: string;
  fiscal: Fiscal;
  event_date: Date;
}): Promise<InsiderMonkeySearchHit | null> {
  const { ticker, fiscal, event_date } = args;
  if (!fiscal.fiscal_year || !fiscal.fiscal_quarter) return null;

  const after = new Date(event_date.getTime() - 60 * 24 * 3600 * 1000).toISOString();
  const before = new Date(event_date.getTime() + 60 * 24 * 3600 * 1000).toISOString();

  const exchanges = ["NASDAQ", "NYSE", "AMEX", "BATS", "NYSEAMERICAN"];
  const q = `Q${fiscal.fiscal_quarter} ${fiscal.fiscal_year} Earnings Call Transcript`;

  for (const ex of exchanges) {
    const query = `(${ex}:${ticker.toUpperCase()}) ${q}`;
    const url =
      `${INSIDERMONKEY_API_BASE}/posts?` +
      new URLSearchParams({
        categories: String(INSIDERMONKEY_TRANSCRIPTS_CATEGORY_ID),
        search: query,
        after,
        before,
        per_page: "5",
        _fields: "id,link,slug,title,date",
      }).toString();

    try {
      const j = (await fetchInsiderMonkeyJson(url)) as InsiderMonkeySearchHit[];
      if (Array.isArray(j) && j.length) return j[0];
    } catch {
      // Try next exchange (some calls may timeout intermittently).
      continue;
    }
  }

  return null;
}

async function fetchInsiderMonkeyPostContent(id: number): Promise<{
  link: string;
  title: string;
  contentHtml: string;
}> {
  const url =
    `${INSIDERMONKEY_API_BASE}/posts/${id}?` +
    new URLSearchParams({ _fields: "link,title,content" }).toString();
  const j = (await fetchInsiderMonkeyJson(url)) as {
    link: string;
    title: { rendered: string };
    content: { rendered: string };
  };
  return {
    link: j.link,
    title: String(j.title?.rendered ?? "").trim(),
    contentHtml: String(j.content?.rendered ?? ""),
  };
}

function parseInsiderMonkeySegmentsFromContentHtml(contentHtml: string): {
  speaker: string;
  text: string;
}[] {
  const $ = cheerio.load(`<div id="im-root">${contentHtml}</div>`);
  const root = $("#im-root");
  const pEls = root.find("p").toArray();

  // Start only once we see a speaker-like paragraph (avoid bullet summaries).
  const start: cheerio.Element[] = [];
  let started = false;
  for (const p of pEls) {
    const t = normalizeWhitespace($(p).text());
    const strong = $(p).find("strong").first();
    const strongText = strong.length ? normalizeWhitespace(strong.text()) : "";
    if (!started) {
      if ((strongText && /:\s*$/.test(strongText)) || /^([^:]{2,80}):\s+/.test(t)) {
        started = true;
      } else {
        continue;
      }
    }
    start.push(p);
  }
  return parseSegmentsFromParagraphs($, start);
}

async function parseEarningsCallArticle(
  item: DiscoveredItem,
  cookieSeed: CookieJar
): Promise<ParsedEarningsCall> {
  const jar = new Map(cookieSeed);
  const html = await fetchHtml(item.source_url, jar);
  const $ = cheerio.load(html);

  const title = extractArticleTitle($);
  if (!title) throw new Error("Could not extract title");

  const eventDate =
    typeof item.event_epoch_seconds === "number"
      ? new Date(item.event_epoch_seconds * 1000)
      : extractEventDate($);
  if (!eventDate || Number.isNaN(eventDate.getTime())) {
    throw new Error("Could not extract event date");
  }

  const fiscalFromTitle = parseFiscalFromTitle(title);
  const fiscalFromUrl = inferFiscalFromYahooUrl(item.source_url);
  const fiscal: Fiscal = {
    fiscal_year:
      fiscalFromTitle.fiscal_year ??
      item.fiscal_year ??
      fiscalFromUrl.fiscal_year ??
      null,
    fiscal_quarter:
      fiscalFromTitle.fiscal_quarter ??
      item.fiscal_quarter ??
      fiscalFromUrl.fiscal_quarter ??
      null,
  };
  const earnings_key = computeEarningsKey(item.ticker, fiscal);

  const participants = extractParticipants($);
  const embeddedJson = extractEmbeddedTranscriptXhrBody(html);
  const segments = embeddedJson ? parseSegmentsFromTranscriptJson(embeddedJson) : [];
  const fallbackSegments = segments.length
    ? segments
    : parseSpeakerSegments(extractTranscriptBodyText($));
  const finalSegments = fallbackSegments;

  if (embeddedJson) {
    const tc = (embeddedJson as Record<string, unknown>).transcriptContent as
      | Record<string, unknown>
      | undefined;
    const t = tc?.transcript as Record<string, unknown> | undefined;
    const textLen = typeof t?.text === "string" ? t.text.length : null;
    const paras = t?.paragraphs as unknown;
    const paraLen = Array.isArray(paras) ? paras.length : null;
    // Many quarters return a stub payload (1 paragraph, empty transcript.text) even though the page loads.
    // Treat as "incomplete" so we can skip + log instead of failing the entire run.
    if ((textLen !== null && textLen < 1000) || (paraLen !== null && paraLen < 10)) {
      throw new IncompleteTranscriptError(
        `INCOMPLETE_TRANSCRIPT textLen=${textLen ?? "?"} paraLen=${paraLen ?? "?"}`,
        {
          ticker: item.ticker,
          title,
          event_date: eventDate,
          fiscal,
          source_url: item.source_url,
          participants,
        }
      );
    }
  }

  if (finalSegments.length < 10) {
    throw new Error(`Too few speaker segments parsed (${finalSegments.length})`);
  }

  return {
    ticker: item.ticker,
    title,
    event_date: eventDate,
    fiscal,
    earnings_key,
    source_url: item.source_url,
    source: "yahoo",
    participants,
    segments: finalSegments,
  };
}

function choosePrimarySpeaker(parsed: ParsedEarningsCall): string {
  if (parsed.participants.ceo) return parsed.participants.ceo;
  // fallback: first non-operator speaker
  const first = parsed.segments.find((s) => !/operator/i.test(s.speaker));
  return first?.speaker ?? parsed.segments[0]?.speaker ?? parsed.ticker;
}

function buildSpeakersPresent(parsed: ParsedEarningsCall): string[] {
  const set = new Map<string, string>();
  const add = (v?: string) => {
    const n = (v ?? "").trim();
    if (!n) return;
    const k = n.toLowerCase();
    if (!set.has(k)) set.set(k, n);
  };
  add(parsed.participants.ceo);
  add(parsed.participants.cfo);
  for (const o of parsed.participants.others) add(o);
  for (const s of parsed.segments) add(s.speaker);
  return Array.from(set.values());
}

async function upsertToDb(parsed: ParsedEarningsCall) {
  const primary = choosePrimarySpeaker(parsed);
  const speakers_present = buildSpeakersPresent(parsed);

  return await prisma.$transaction(async (tx) => {
    const where = parsed.earnings_key
      ? { earnings_key: parsed.earnings_key }
      : { source_url: parsed.source_url };
    const t = await tx.transcript.upsert({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      where: where as any,
      create: {
        title: parsed.title,
        event_date: parsed.event_date,
        speech_type: "Earnings Call",
        primary_speaker: primary,
        speakers_present,
        has_q_and_a: true, // earnings calls almost always have Q&A; safe default
        total_speech_length_seconds: null,
        key_themes: [],
        question_count: null,
        avg_response_length_words: null,
        avg_response_length_seconds: null,
        qa_data: null,

        company_ticker: parsed.ticker,
        fiscal_year: parsed.fiscal.fiscal_year,
        fiscal_quarter: parsed.fiscal.fiscal_quarter,
        source: parsed.source,
        source_url: parsed.source_url,
        earnings_key: parsed.earnings_key,
      },
      update: {
        title: parsed.title,
        event_date: parsed.event_date,
        speech_type: "Earnings Call",
        primary_speaker: primary,
        speakers_present,
        company_ticker: parsed.ticker,
        fiscal_year: parsed.fiscal.fiscal_year,
        fiscal_quarter: parsed.fiscal.fiscal_quarter,
        source: parsed.source,
        source_url: parsed.source_url,
        earnings_key: parsed.earnings_key,
      },
      select: { id: true },
    });

    await tx.speakingSegment.deleteMany({ where: { transcriptId: t.id } });

    // Chunk to avoid exceeding parameter limits
    const data = parsed.segments.map((s, idx) => ({
      transcriptId: t.id,
      speaker: s.speaker,
      start_seconds: idx,
      end_seconds: idx + 1,
      text: s.text,
    }));

    const chunkSize = 500;
    for (let i = 0; i < data.length; i += chunkSize) {
      await tx.speakingSegment.createMany({ data: data.slice(i, i + chunkSize) });
    }

    return { transcriptId: t.id, segmentCount: parsed.segments.length };
  });
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  const outDir = resolve(process.cwd(), opts.outDir);
  ensureDir(outDir);

  const runId = nowIsoCompact();
  const logPath = resolve(outDir, `yahoo-earnings-${runId}.jsonl`);
  writeFileSync(
    resolve(outDir, `yahoo-earnings-${runId}.meta.json`),
    JSON.stringify(
      {
        runId,
        startedAt: new Date().toISOString(),
        options: opts,
      },
      null,
      2
    ),
    "utf8"
  );

  const limit = pLimit(opts.concurrency);

  for (const ticker of opts.tickers) {
    logJsonl(logPath, { type: "ticker_start", ticker, at: new Date().toISOString() });

    let discovered: DiscoveredItem[] = [];
    let cookieSeed: CookieJar = new Map();
    try {
      const r = await discoverForTicker(ticker);
      discovered = r.items;
      cookieSeed = r.cookieSeed;
      logJsonl(logPath, {
        type: "discover_ok",
        ticker,
        count: discovered.length,
        at: new Date().toISOString(),
      });
    } catch (err) {
      logJsonl(logPath, {
        type: "discover_error",
        ticker,
        error: err instanceof Error ? err.message : String(err),
        at: new Date().toISOString(),
      });
      continue;
    }

    // Dedup within ticker
    const unique = new Map<string, DiscoveredItem>();
    for (const it of discovered) unique.set(it.source_url, it);
    const urls = Array.from(unique.values());

    const jobs = urls.map((it) =>
      limit(async () => {
        await sleep(opts.delayMs);
        try {
          const parsed = await parseEarningsCallArticle(it, cookieSeed);
          if (isBelowMinFiscal(parsed.fiscal, opts.minFiscalYear, opts.minFiscalQuarter)) {
            logJsonl(logPath, {
              type: "skipped_below_min_fiscal",
              ticker,
              source_url: it.source_url,
              fiscal: parsed.fiscal,
              title: parsed.title,
              at: new Date().toISOString(),
            });
            return;
          }

          if (opts.dryRun) {
            logJsonl(logPath, {
              type: "parsed_dry_run",
              ticker,
              source_url: it.source_url,
              earnings_key: parsed.earnings_key,
              source: parsed.source,
              title: parsed.title,
              event_date: parsed.event_date.toISOString(),
              fiscal: parsed.fiscal,
              segmentCount: parsed.segments.length,
              at: new Date().toISOString(),
            });
            return;
          }

          const up = await upsertToDb(parsed);
          logJsonl(logPath, {
            type: "upsert_ok",
            ticker,
            source_url: it.source_url,
            earnings_key: parsed.earnings_key,
            source: parsed.source,
            title: parsed.title,
            transcriptId: up.transcriptId,
            segmentCount: up.segmentCount,
            at: new Date().toISOString(),
          });
        } catch (err) {
          if (err instanceof IncompleteTranscriptError) {
            const msg = err.message;

            logJsonl(logPath, {
              type: "yahoo_incomplete_transcript",
              ticker,
              source_url: it.source_url,
              earnings_key: computeEarningsKey(ticker, err.meta.fiscal),
              reason: msg,
              at: new Date().toISOString(),
            });

            // Fallback 1: InsiderMonkey (free, full text via WP API)
            try {
              const hit = await findInsiderMonkeyTranscriptPost({
                ticker,
                fiscal: err.meta.fiscal,
                event_date: err.meta.event_date,
              });
              if (hit) {
                const post = await fetchInsiderMonkeyPostContent(hit.id);
                const segments = parseInsiderMonkeySegmentsFromContentHtml(post.contentHtml);
                if (segments.length >= 10) {
                  const parsed: ParsedEarningsCall = {
                    ticker,
                    title: post.title || err.meta.title || "InsiderMonkey",
                    event_date: err.meta.event_date,
                    fiscal: err.meta.fiscal,
                    earnings_key: computeEarningsKey(ticker, err.meta.fiscal),
                    source_url: post.link,
                    source: "insidermonkey",
                    participants: err.meta.participants,
                    segments,
                  };

                  if (opts.dryRun) {
                    logJsonl(logPath, {
                      type: "parsed_dry_run",
                      ticker,
                      source_url: parsed.source_url,
                      earnings_key: parsed.earnings_key,
                      source: parsed.source,
                      title: parsed.title,
                      event_date: parsed.event_date.toISOString(),
                      fiscal: parsed.fiscal,
                      segmentCount: parsed.segments.length,
                      at: new Date().toISOString(),
                    });
                    return;
                  }

                  const up = await upsertToDb(parsed);
                  logJsonl(logPath, {
                    type: "upsert_ok",
                    ticker,
                    source_url: parsed.source_url,
                    earnings_key: parsed.earnings_key,
                    source: parsed.source,
                    title: parsed.title,
                    transcriptId: up.transcriptId,
                    segmentCount: up.segmentCount,
                    at: new Date().toISOString(),
                  });
                  return;
                }
              }
            } catch (e2) {
              logJsonl(logPath, {
                type: "fallback_error",
                ticker,
                provider: "insidermonkey",
                source_url: it.source_url,
                earnings_key: computeEarningsKey(ticker, err.meta.fiscal),
                error: e2 instanceof Error ? e2.message : String(e2),
                at: new Date().toISOString(),
              });
            }

            // Fallback 2: Motley Fool (free, full transcript in monthly sitemaps)
            try {
              const mfUrl = await findMotleyFoolTranscriptUrl({
                ticker,
                fiscal: err.meta.fiscal,
                event_date: err.meta.event_date,
              });
              if (mfUrl) {
                const mf = await parseMotleyFoolTranscript({
                  ticker,
                  fiscal: err.meta.fiscal,
                  event_date: err.meta.event_date,
                  url: mfUrl,
                });

                const parsed: ParsedEarningsCall = {
                  ticker,
                  title: mf.title || err.meta.title || "Motley Fool",
                  event_date: err.meta.event_date,
                  fiscal: err.meta.fiscal,
                  earnings_key: computeEarningsKey(ticker, err.meta.fiscal),
                  source_url: mfUrl,
                  source: "motleyfool",
                  participants: mf.participants,
                  segments: mf.segments,
                };

                if (opts.dryRun) {
                  logJsonl(logPath, {
                    type: "parsed_dry_run",
                    ticker,
                    source_url: parsed.source_url,
                    earnings_key: parsed.earnings_key,
                    source: parsed.source,
                    title: parsed.title,
                    event_date: parsed.event_date.toISOString(),
                    fiscal: parsed.fiscal,
                    segmentCount: parsed.segments.length,
                    at: new Date().toISOString(),
                  });
                  return;
                }

                const up = await upsertToDb(parsed);
                logJsonl(logPath, {
                  type: "upsert_ok",
                  ticker,
                  source_url: parsed.source_url,
                  earnings_key: parsed.earnings_key,
                  source: parsed.source,
                  title: parsed.title,
                  transcriptId: up.transcriptId,
                  segmentCount: up.segmentCount,
                  at: new Date().toISOString(),
                });
                return;
              }
            } catch (e3) {
              logJsonl(logPath, {
                type: "fallback_error",
                ticker,
                provider: "motleyfool",
                source_url: it.source_url,
                earnings_key: computeEarningsKey(ticker, err.meta.fiscal),
                error: e3 instanceof Error ? e3.message : String(e3),
                at: new Date().toISOString(),
              });
            }

            if (opts.requireComplete) {
              logJsonl(logPath, {
                type: "item_error",
                ticker,
                source_url: it.source_url,
                earnings_key: computeEarningsKey(ticker, err.meta.fiscal),
                error: "COMPLETE_TRANSCRIPT_REQUIRED but all fallbacks failed",
                at: new Date().toISOString(),
              });
              return;
            }

            // Old behavior (optional): allow skipping incomplete when requireComplete=false
            logJsonl(logPath, {
              type: "skipped_incomplete_transcript",
              ticker,
              source_url: it.source_url,
              earnings_key: computeEarningsKey(ticker, err.meta.fiscal),
              reason: msg,
              at: new Date().toISOString(),
            });
            return;
          }

          const msg = err instanceof Error ? err.message : String(err);
          logJsonl(logPath, {
            type: "item_error",
            ticker,
            source_url: it.source_url,
            error: msg,
            at: new Date().toISOString(),
          });
        }
      })
    );

    await Promise.all(jobs);
    logJsonl(logPath, { type: "ticker_done", ticker, at: new Date().toISOString() });
  }

  logJsonl(logPath, { type: "run_done", at: new Date().toISOString() });

  await prisma.$disconnect();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});

