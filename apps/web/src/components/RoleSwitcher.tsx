// Citizen/officer role switcher — POC stand-in for auth (SPEC §3 OUT).
// Client component: persists choice in localStorage; B3/B4 routes will read it
// (and can be deep-linked independently — this is a navigator, not a gate).

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

export type Role = "citizen" | "officer";

const ROLES: { id: Role; label: string; href: string }[] = [
  { id: "citizen", label: "Citizen", href: "/citizen" },
  { id: "officer", label: "Officer", href: "/officer" },
];

const STORAGE_KEY = "sewasetu.role";

export function RoleSwitcher() {
  const [role, setRole] = useState<Role>("citizen");

  // Restore after mount only — keeps SSR markup deterministic (no hydration diff).
  useEffect(() => {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (saved === "officer" || saved === "citizen") setRole(saved);
  }, []);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, role);
  }, [role]);

  return (
    <div
      role="group"
      aria-label="Role switcher"
      className="flex items-center gap-1 rounded-full border border-zinc-200 bg-white p-1"
    >
      {ROLES.map((r) => (
        <Link
          key={r.id}
          href={r.href}
          aria-pressed={role === r.id}
          onClick={() => setRole(r.id)}
          className={`inline-flex min-h-12 items-center justify-center rounded-full px-4 py-2 text-sm font-medium transition-colors ${
            role === r.id
              ? "bg-brand-600 text-white shadow-sm"
              : "text-zinc-600 hover:bg-brand-50 hover:text-brand-700"
          }`}
        >
          {r.label}
        </Link>
      ))}
    </div>
  );
}
