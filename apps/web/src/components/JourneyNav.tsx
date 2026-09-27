"use client";

// Role-aware secondary navigation (B8+ polish): keeps every screen in the
// current journey reachable from the shell. Server Component can't use
// usePathname, so this small client island renders the active tab. Hidden on
// the landing page (no journey prefix).

import Link from "next/link";
import { usePathname } from "next/navigation";

type NavItem = { href: string; label: string; match: (p: string) => boolean };

const JOURNEYS: { prefix: string; items: NavItem[] }[] = [
  {
    prefix: "/citizen",
    items: [
      {
        href: "/citizen",
        label: "Services",
        match: (p) => !p.startsWith("/citizen/apps"),
      },
      {
        href: "/citizen/apps",
        label: "My applications",
        match: (p) => p.startsWith("/citizen/apps"),
      },
    ],
  },
  {
    prefix: "/officer",
    items: [
      {
        href: "/officer",
        label: "Queue",
        match: (p) => !p.startsWith("/officer/dashboard"),
      },
      {
        href: "/officer/dashboard",
        label: "Metrics",
        match: (p) => p.startsWith("/officer/dashboard"),
      },
    ],
  },
];

export function JourneyNav() {
  const pathname = usePathname();
  const journey = JOURNEYS.find(
    (j) => pathname === j.prefix || pathname.startsWith(j.prefix + "/"),
  );
  if (!journey) return null;

  return (
    <nav aria-label="Section" className="border-t border-zinc-200 bg-white">
      <div className="mx-auto flex w-full max-w-5xl items-center gap-1 px-4">
        {journey.items.map((item) => {
          const active = item.match(pathname);
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={`min-h-12 border-b-2 px-3 py-2 text-sm font-medium transition-colors ${
                active
                  ? "border-brand-600 text-brand-700"
                  : "border-transparent text-zinc-500 hover:text-brand-700"
              }`}
            >
              {item.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
