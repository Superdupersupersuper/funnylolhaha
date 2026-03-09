import Link from "next/link";

export default function HomePage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8">
      <h1 className="text-4xl font-bold tracking-tight">MentionMarkets</h1>
      <p className="mt-4 text-center text-muted-foreground">
        Transcript intelligence for prediction markets.
        <br />
        Search mentions across speeches, press conferences, and earnings calls.
      </p>
      <div className="mt-8 flex flex-wrap justify-center gap-4">
        <Link
          href="/search"
          className="rounded-md bg-primary px-6 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          Search Transcripts
        </Link>
        <Link
          href="/earnings"
          className="rounded-md border border-input px-6 py-2.5 text-sm font-medium hover:bg-accent"
        >
          Earnings Calls
        </Link>
        <Link
          href="/admin/transcripts"
          className="rounded-md border border-input px-6 py-2.5 text-sm font-medium opacity-50 hover:bg-accent hover:opacity-100"
        >
          Admin
        </Link>
      </div>
    </main>
  );
}
