import Link from "next/link";
import { LogoutButton } from "@/components/admin/LogoutButton";

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen">
      {/* Admin nav bar */}
      <header className="border-b border-border bg-card">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3">
          <div className="flex items-center gap-6">
            <Link
              href="/admin/transcripts"
              className="text-lg font-bold tracking-tight"
            >
              MentionMarkets{" "}
              <span className="text-xs font-normal text-muted-foreground">
                Admin
              </span>
            </Link>
            <nav className="flex gap-4 text-sm">
              <Link
                href="/admin/transcripts"
                className="text-muted-foreground hover:text-foreground"
              >
                Transcripts
              </Link>
              <Link
                href="/admin/transcripts/new"
                className="text-muted-foreground hover:text-foreground"
              >
                Upload New
              </Link>
              <Link
                href="/admin/qa-training"
                className="text-muted-foreground hover:text-foreground"
              >
                Q&amp;A Training
              </Link>
            </nav>
          </div>
          <LogoutButton />
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
    </div>
  );
}
