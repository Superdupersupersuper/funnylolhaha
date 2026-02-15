import Link from "next/link";
import { prisma } from "@/lib/db";

export const dynamic = "force-dynamic";

export default async function TranscriptListPage() {
  let transcripts: Awaited<ReturnType<typeof fetchTranscripts>> = [];
  let dbError = "";

  try {
    transcripts = await fetchTranscripts();
  } catch (err) {
    dbError =
      err instanceof Error ? err.message : "Could not connect to database.";
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Transcripts</h1>
        <Link
          href="/admin/transcripts/new"
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          + Upload New
        </Link>
      </div>

      {dbError && (
        <div className="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <strong>Database error:</strong> {dbError}
          <p className="mt-1 text-xs text-muted-foreground">
            Make sure DATABASE_URL is configured and the database has been migrated
            (run <code>npx prisma db push</code> in the web/ directory).
          </p>
        </div>
      )}

      {!dbError && transcripts.length === 0 && (
        <div className="rounded-lg border border-dashed border-border p-8 text-center text-muted-foreground">
          No transcripts yet.{" "}
          <Link href="/admin/transcripts/new" className="text-primary underline">
            Upload your first one
          </Link>
          .
        </div>
      )}

      {transcripts.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/50">
                <th className="px-4 py-2.5 text-left font-medium">Date</th>
                <th className="px-4 py-2.5 text-left font-medium">Title</th>
                <th className="px-4 py-2.5 text-left font-medium">Speaker</th>
                <th className="px-4 py-2.5 text-left font-medium">Type</th>
                <th className="px-4 py-2.5 text-right font-medium">Segments</th>
                <th className="px-4 py-2.5 text-right font-medium">Duration</th>
                <th className="px-4 py-2.5 text-left font-medium">Themes</th>
                <th className="px-4 py-2.5" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {transcripts.map((t) => (
                <tr key={t.id} className="hover:bg-muted/30">
                  <td className="whitespace-nowrap px-4 py-2">
                    {new Date(t.event_date).toLocaleDateString()}
                  </td>
                  <td className="max-w-[280px] truncate px-4 py-2 font-medium">
                    {t.title}
                  </td>
                  <td className="px-4 py-2">{t.primary_speaker}</td>
                  <td className="px-4 py-2">{t.speech_type}</td>
                  <td className="px-4 py-2 text-right">
                    {t._count.segments}
                  </td>
                  <td className="px-4 py-2 text-right">
                    {t.total_speech_length_seconds
                      ? formatDuration(t.total_speech_length_seconds)
                      : "—"}
                  </td>
                  <td className="px-4 py-2">
                    <div className="flex flex-wrap gap-1">
                      {t.key_themes.slice(0, 3).map((th) => (
                        <span
                          key={th}
                          className="inline-block rounded bg-secondary px-1.5 py-0.5 text-xs"
                        >
                          {th}
                        </span>
                      ))}
                      {t.key_themes.length > 3 && (
                        <span className="text-xs text-muted-foreground">
                          +{t.key_themes.length - 3}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-2 text-right">
                    <Link
                      href={`/admin/transcripts/${t.id}/edit`}
                      className="text-primary hover:underline"
                    >
                      Edit
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

async function fetchTranscripts() {
  return prisma.transcript.findMany({
    orderBy: { event_date: "desc" },
    select: {
      id: true,
      title: true,
      event_date: true,
      speech_type: true,
      primary_speaker: true,
      has_q_and_a: true,
      total_speech_length_seconds: true,
      key_themes: true,
      _count: { select: { segments: true } },
    },
  });
}

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

