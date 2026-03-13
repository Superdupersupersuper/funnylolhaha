/**
 * Backfill Q&A detection for all existing earnings call transcripts.
 *
 * Works via the Next.js admin API (no direct DB connection required).
 *
 * Usage:
 *   npx tsx scripts/backfill_earnings_qa.ts --password=<admin_pw>
 *   npx tsx scripts/backfill_earnings_qa.ts --password=<admin_pw> --ticker=NFLX
 *   npx tsx scripts/backfill_earnings_qa.ts --password=<admin_pw> --dry-run
 */

import { detectEarningsQA } from "../src/lib/parsers/earnings-qa";

const NEXTJS_BASE = "https://mention-markets-web.onrender.com";

interface TranscriptMeta {
  id: string;
  title: string;
  company_ticker: string | null;
  fiscal_year: number | null;
  fiscal_quarter: number | null;
  speakers_present: string[];
  primary_speaker: string;
}

interface Segment {
  speaker: string;
  start_seconds: number;
  end_seconds: number | null;
  text: string;
}

async function main() {
  const args = process.argv.slice(2);
  const dryRun = args.includes("--dry-run");
  const pwArg = args.find((a) => a.startsWith("--password="));
  const tickerArg = args.find((a) => a.startsWith("--ticker="));
  const password = pwArg ? pwArg.split("=")[1] : "";
  const tickerFilter = tickerArg ? tickerArg.split("=")[1].toUpperCase() : null;

  if (!password) {
    console.error("Usage: npx tsx scripts/backfill_earnings_qa.ts --password=<admin_pw>");
    process.exit(1);
  }

  console.log(
    `\n=== Earnings Q&A Backfill ===` +
      (dryRun ? " [DRY RUN]" : "") +
      (tickerFilter ? ` [ticker=${tickerFilter}]` : " [all companies]") +
      "\n"
  );

  // Authenticate with the admin API
  const loginResp = await fetch(`${NEXTJS_BASE}/api/admin/auth`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
  if (!loginResp.ok) {
    console.error("Admin login failed:", loginResp.status);
    process.exit(1);
  }
  const cookies = loginResp.headers.getSetCookie?.() || [];
  const cookieHeader = cookies.join("; ");
  console.log("Authenticated with admin API.\n");

  // Load all earnings companies
  const listUrl = tickerFilter
    ? `${NEXTJS_BASE}/api/earnings?ticker=${tickerFilter}`
    : `${NEXTJS_BASE}/api/earnings`;
  const listResp = await fetch(listUrl);
  const listData = (await listResp.json()) as {
    companies: Array<{ ticker: string; transcripts: TranscriptMeta[] }>;
    total: number;
  };

  const companies = listData.companies || [];
  const allTranscripts = companies.flatMap((c) => c.transcripts);
  console.log(
    `Found ${companies.length} companies, ${allTranscripts.length} transcripts.\n`
  );

  let updated = 0;
  let skipped = 0;
  let totalPairs = 0;
  let errors = 0;

  for (const t of allTranscripts) {
    const label = `${t.company_ticker} FY${t.fiscal_year} Q${t.fiscal_quarter}`;

    // Fetch full transcript with segments
    let data: { transcript: { segments: Segment[]; speakers_present: string[]; primary_speaker: string } } | null =
      null;
    try {
      const resp = await fetch(`${NEXTJS_BASE}/api/earnings?id=${t.id}`);
      if (resp.ok) data = (await resp.json()) as typeof data;
    } catch {}

    if (!data?.transcript?.segments?.length) {
      console.log(`  SKIP  ${label} — no segments`);
      skipped++;
      continue;
    }

    const segments = data.transcript.segments;
    const reps = [...(data.transcript.speakers_present || [])];
    const hasOperator = segments.some((s: Segment) => /^operator$/i.test(s.speaker));
    if (hasOperator && !reps.some((r: string) => /^operator$/i.test(r))) {
      reps.push("Operator");
    }

    const result = detectEarningsQA(
      segments.map((s: Segment) => ({
        speaker: s.speaker,
        start_seconds: s.start_seconds,
        end_seconds: s.end_seconds,
        text: s.text,
      })),
      reps
    );

    totalPairs += result.question_count;

    if (dryRun) {
      console.log(
        `  WOULD UPDATE  ${label} — ${result.question_count} Q&A pairs, ` +
          `avg ${result.avg_response_length_words ?? 0} words/response`
      );
      updated++;
      continue;
    }

    // PATCH via the admin transcripts API
    try {
      const patchResp = await fetch(
        `${NEXTJS_BASE}/api/admin/transcripts/${t.id}`,
        {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            Cookie: cookieHeader,
          },
          body: JSON.stringify({
            has_q_and_a: result.has_q_and_a,
            question_count: result.question_count,
            avg_response_length_words: result.avg_response_length_words,
            avg_response_length_seconds: result.avg_response_length_seconds,
            qa_data: result.qa_data,
            qa_data_auto: result.qa_data_auto,
          }),
        }
      );
      if (!patchResp.ok) {
        console.log(
          `  ERROR  ${label} — HTTP ${patchResp.status}: ${await patchResp.text()}`
        );
        errors++;
        continue;
      }
    } catch (e: unknown) {
      console.log(`  ERROR  ${label} — ${(e as Error).message}`);
      errors++;
      continue;
    }

    console.log(
      `  OK  ${label} — ${result.question_count} Q&A pairs, ` +
        `avg ${result.avg_response_length_words ?? 0} words/response`
    );
    updated++;

    // Small rate-limit to avoid hammering the API
    await new Promise((r) => setTimeout(r, 200));
  }

  console.log(
    `\nDone. Updated: ${updated}, Skipped: ${skipped}, Errors: ${errors}, Total Q&A pairs: ${totalPairs}\n`
  );
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
