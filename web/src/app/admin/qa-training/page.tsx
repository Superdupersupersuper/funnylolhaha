import Link from "next/link";
import { prisma } from "@/lib/db";

export const dynamic = "force-dynamic";

export default async function QATrainingPage() {
  let transcripts: Awaited<ReturnType<typeof fetchData>>["transcripts"] = [];
  let stats = { totalYes: 0, totalNo: 0, total: 0 };
  let dbError = "";

  try {
    const data = await fetchData();
    transcripts = data.transcripts;
    stats = data.stats;
  } catch (err) {
    dbError = err instanceof Error ? err.message : "Could not connect to database.";
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Q&A Training</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Label exchanges as Q&A or not Q&A. Your labels become few-shot examples for the AI classifier.
          </p>
        </div>
      </div>

      {/* Global stats */}
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="rounded-lg border border-border bg-card p-4">
          <div className="text-sm text-muted-foreground">Total labels</div>
          <div className="mt-1 text-3xl font-bold">{stats.total}</div>
        </div>
        <div className="rounded-lg border border-border bg-card p-4">
          <div className="text-sm text-green-600 font-medium">Labeled Q&A</div>
          <div className="mt-1 text-3xl font-bold text-green-700">{stats.totalYes}</div>
        </div>
        <div className="rounded-lg border border-border bg-card p-4">
          <div className="text-sm text-red-500 font-medium">Labeled Not Q&A</div>
          <div className="mt-1 text-3xl font-bold text-red-600">{stats.totalNo}</div>
        </div>
      </div>

      {stats.total < 20 && (
        <div className="rounded-md border border-yellow-200 bg-yellow-50 px-4 py-3 text-sm text-yellow-800">
          <strong>Getting started:</strong> Label at least 20 examples (mix of Yes and No) before the AI classifier will be activated. You have {stats.total} so far.
        </div>
      )}

      {dbError && (
        <div className="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {dbError}
        </div>
      )}

      {!dbError && transcripts.length === 0 && (
        <div className="rounded-lg border border-dashed border-border p-8 text-center text-muted-foreground">
          No transcripts with Q&A found.{" "}
          <Link href="/admin/transcripts" className="text-primary underline">
            Mark some transcripts as having Q&A
          </Link>{" "}
          first.
        </div>
      )}

      {transcripts.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/50">
                <th className="px-4 py-2.5 text-left font-medium">Date</th>
                <th className="px-4 py-2.5 text-left font-medium">Transcript</th>
                <th className="px-4 py-2.5 text-left font-medium">Speaker</th>
                <th className="px-4 py-2.5 text-right font-medium">Candidates</th>
                <th className="px-4 py-2.5 text-right font-medium">Labeled</th>
                <th className="px-4 py-2.5 text-right font-medium">Progress</th>
                <th className="px-4 py-2.5" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {transcripts.map((t) => {
                const pct =
                  t.candidateCount > 0
                    ? Math.round((t.labelCount / t.candidateCount) * 100)
                    : 0;
                const done = t.candidateCount > 0 && t.labelCount >= t.candidateCount;
                return (
                  <tr key={t.id} className="hover:bg-muted/30">
                    <td className="whitespace-nowrap px-4 py-2 text-muted-foreground">
                      {new Date(t.event_date).toLocaleDateString()}
                    </td>
                    <td className="max-w-[280px] truncate px-4 py-2 font-medium">
                      {t.title}
                    </td>
                    <td className="px-4 py-2 text-muted-foreground">
                      {t.primary_speaker}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">
                      {t.candidateCount}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">
                      {t.labelCount}
                    </td>
                    <td className="px-4 py-2 text-right">
                      {t.candidateCount === 0 ? (
                        <span className="text-muted-foreground text-xs">no segments</span>
                      ) : done ? (
                        <span className="rounded bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
                          Complete
                        </span>
                      ) : (
                        <div className="flex items-center justify-end gap-2">
                          <div className="h-1.5 w-20 overflow-hidden rounded-full bg-muted">
                            <div
                              className="h-full rounded-full bg-primary"
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                          <span className="text-xs text-muted-foreground tabular-nums">
                            {pct}%
                          </span>
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-2 text-right">
                      <Link
                        href={`/admin/qa-training/${t.id}`}
                        className="rounded-md bg-primary px-3 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/90"
                      >
                        {t.labelCount > 0 ? "Continue" : "Label"}
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

async function fetchData() {
  const [rawTranscripts, allLabels] = await Promise.all([
    prisma.transcript.findMany({
      where: { has_q_and_a: true },
      orderBy: { event_date: "desc" },
      select: {
        id: true,
        title: true,
        event_date: true,
        primary_speaker: true,
        segments: {
          select: { speaker: true, start_seconds: true, text: true },
          orderBy: { start_seconds: "asc" },
        },
      },
    }),
    prisma.qALabel.findMany({ select: { transcriptId: true } }),
  ]);

  const [totalYes, totalNo] = await Promise.all([
    prisma.qALabel.count({ where: { isQA: true } }),
    prisma.qALabel.count({ where: { isQA: false } }),
  ]);

  // Count labels per transcript
  const labelCountMap: Record<string, number> = {};
  for (const l of allLabels) {
    labelCountMap[l.transcriptId] = (labelCountMap[l.transcriptId] ?? 0) + 1;
  }

  // Count candidate exchanges per transcript
  const transcripts = rawTranscripts.map((t) => {
    // Simple candidate count: non-primary, ≥10 words, followed by primary response
    const primarySpeaker = t.primary_speaker;
    let candidateCount = 0;
    const segs = t.segments;
    for (let i = 0; i < segs.length; i++) {
      const seg = segs[i];
      if (seg.speaker === primarySpeaker) continue;
      const wc = seg.text.split(/\s+/).filter(Boolean).length;
      if (wc < 10) continue;
      // Check if followed by primary speaker
      const hasResponse = segs.slice(i + 1).some((s) => s.speaker === primarySpeaker);
      if (hasResponse) candidateCount++;
    }
    return {
      id: t.id,
      title: t.title,
      event_date: t.event_date,
      primary_speaker: t.primary_speaker,
      candidateCount,
      labelCount: labelCountMap[t.id] ?? 0,
    };
  });

  return {
    transcripts,
    stats: { totalYes, totalNo, total: totalYes + totalNo },
  };
}
