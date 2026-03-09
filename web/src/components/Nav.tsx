import Link from "next/link";

const links = [
  { href: "/search", label: "Search" },
  { href: "/earnings", label: "Earnings Calls" },
];

export default function Nav({ active }: { active?: "search" | "earnings" }) {
  return (
    <nav className="sticky top-0 z-40 border-b border-zinc-800 bg-zinc-950/80 backdrop-blur">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
        <Link href="/" className="text-sm font-bold tracking-tight text-zinc-100 hover:text-white">
          MentionMarkets
        </Link>
        <div className="flex items-center gap-1">
          {links.map(({ href, label }) => {
            const isActive = active === href.slice(1);
            return (
              <Link
                key={href}
                href={href}
                className={`rounded-full px-3.5 py-1.5 text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-zinc-800 text-white"
                    : "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200"
                }`}
              >
                {label}
              </Link>
            );
          })}
        </div>
      </div>
    </nav>
  );
}
