import type { Metadata } from "next";
import Link from "next/link";
import localFont from "next/font/local";
import { RoleSwitcher } from "@/components/RoleSwitcher";
import "./globals.css";

const geistSans = localFont({
  src: "./fonts/GeistVF.woff",
  variable: "--font-geist-sans",
  weight: "100 900",
});
const geistMono = localFont({
  src: "./fonts/GeistMonoVF.woff",
  variable: "--font-geist-mono",
  weight: "100 900",
});

export const metadata: Metadata = {
  title: "Sewa Setu Scrutiny POC",
  description:
    "Agentic application scrutiny & document verification — citizen + officer workbench",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} flex min-h-screen flex-col bg-zinc-50 text-zinc-900 antialiased`}
      >
        <header className="sticky top-0 z-10 border-b border-zinc-200 bg-white/90 backdrop-blur">
          <div className="mx-auto flex w-full max-w-5xl items-center justify-between gap-4 px-4 py-2">
            <Link href="/" className="text-base font-bold tracking-tight">
              Sewa Setu{" "}
              <span className="font-normal text-zinc-500">Scrutiny POC</span>
            </Link>
            <RoleSwitcher />
          </div>
        </header>
        <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8">
          {children}
        </main>
        <footer className="border-t border-zinc-200 bg-white">
          <div className="mx-auto w-full max-w-5xl px-4 py-3 text-xs text-zinc-500">
            POC — synthetic data only · agent recommends, officer decides
          </div>
        </footer>
      </body>
    </html>
  );
}
