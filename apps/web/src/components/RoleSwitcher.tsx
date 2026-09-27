// Citizen/officer role switcher — POC stand-in for auth (SPEC §3 OUT).
// A navigator, not a gate: it links to each journey's root and highlights the
// one you're currently in. On the landing page neither is active (you haven't
// chosen yet) — the pressed state is derived from the path, not a stored guess.

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

type Role = "citizen" | "officer";

const ROLES: { id: Role; label: string; href: string }[] = [
  { id: "citizen", label: "Citizen", href: "/citizen" },
  { id: "officer", label: "Officer", href: "/officer" },
];

export function RoleSwitcher() {
  const pathname = usePathname();
  const active: Role | null = pathname.startsWith("/citizen")
    ? "citizen"
    : pathname.startsWith("/officer")
      ? "officer"
      : null;

  return (
    <div
      role="group"
      aria-label="Role switcher"
      className="flex items-center gap-1 rounded-full border border-zinc-200 bg-white p-1"
    >
      {ROLES.map((r) => {
        const on = active === r.id;
        return (
          <Link
            key={r.id}
            href={r.href}
            aria-current={on ? "page" : undefined}
            className={`inline-flex min-h-12 items-center justify-center rounded-full px-4 py-2 text-sm font-medium transition-colors ${
              on
                ? "bg-brand-600 text-white shadow-sm"
                : "text-zinc-600 hover:bg-brand-50 hover:text-brand-700"
            }`}
          >
            {r.label}
          </Link>
        );
      })}
    </div>
  );
}
