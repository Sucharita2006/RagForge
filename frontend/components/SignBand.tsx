"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { Arrow, Cross, Menu } from "@/components/icons";

// Pages grouped by the job they do. Query sits apart: it is where you start.
const GROUPS = [
  {
    name: "Inspect",
    pages: [
      { href: "/candidates", label: "Candidates" },
      { href: "/timeline", label: "Timeline" },
    ],
  },
  {
    name: "Measure",
    pages: [
      { href: "/golden-set", label: "Golden set" },
      { href: "/ab", label: "A/B" },
      { href: "/metrics", label: "Metrics" },
    ],
  },
  {
    name: "Improve",
    pages: [
      { href: "/feedback-loop", label: "Feedback loop" },
      { href: "/trust-settings", label: "Trust settings" },
    ],
  },
];

const ON_BAND = "focus-visible:outline-white";

/** A magenta band of three groups; the open group's pages form a second row. */
export function SignBand() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const group = GROUPS.find((g) => g.pages.some((p) => p.href === pathname));
  const page = group?.pages.find((p) => p.href === pathname);
  const onQuery = pathname === "/";

  return (
    <header className="sticky top-0 z-40">
      <div className="bg-sign text-white">
        <div className="mx-auto flex h-14 max-w-page items-center px-4 sm:px-6">
          <Link
            href="/"
            className={`mr-8 text-[1.375rem] font-extrabold tracking-[-0.02em] ${ON_BAND}`}
          >
            ragforge
          </Link>

          <nav aria-label="Page groups" className="hidden h-full items-stretch md:flex">
            {GROUPS.map((g) => (
              <Link
                key={g.name}
                href={g.pages[0].href}
                aria-current={g === group ? "true" : undefined}
                className={`flex items-center px-4 text-[0.9375rem] font-semibold text-white/85 transition-colors duration-150 hover:bg-white/10 hover:text-white aria-[current=true]:bg-white aria-[current=true]:text-sign ${ON_BAND}`}
              >
                {g.name}
              </Link>
            ))}
          </nav>

          <Link
            href="/"
            aria-current={onQuery ? "page" : undefined}
            className={`ml-auto hidden h-9 items-center gap-2 rounded-md bg-white px-4 text-[0.9375rem] font-bold text-sign transition-colors duration-150 hover:bg-white/90 aria-[current=page]:ring-2 aria-[current=page]:ring-white aria-[current=page]:ring-offset-2 aria-[current=page]:ring-offset-sign md:flex ${ON_BAND}`}
          >
            Query
            <Arrow className="h-4 w-4" />
          </Link>

          <div className="ml-auto flex items-center gap-3 md:hidden">
            <span className="text-[0.9375rem] font-semibold">
              {onQuery ? "Query" : (page?.label ?? "")}
            </span>
            <button
              type="button"
              aria-expanded={open}
              aria-controls="all-pages"
              onClick={() => setOpen(!open)}
              className={`inline-flex h-9 w-9 items-center justify-center rounded bg-white text-sign transition-colors duration-150 hover:bg-white/90 ${ON_BAND}`}
            >
              {open ? <Cross /> : <Menu />}
              <span className="sr-only">{open ? "Close the page list" : "All pages"}</span>
            </button>
          </div>
        </div>
      </div>

      {group && (
        <nav aria-label={group.name} className="hidden border-b border-rule bg-card md:block">
          <div className="mx-auto flex h-12 max-w-page items-stretch gap-7 px-4 sm:px-6">
            {group.pages.map((p) => (
              <Link
                key={p.href}
                href={p.href}
                aria-current={p.href === pathname ? "page" : undefined}
                className="flex items-center border-b-[3px] border-transparent pt-[3px] text-[0.9375rem] font-semibold text-ink-2 transition-colors duration-150 hover:text-ink aria-[current=page]:border-sign aria-[current=page]:text-ink"
              >
                {p.label}
              </Link>
            ))}
          </div>
        </nav>
      )}

      {open && (
        <nav
          id="all-pages"
          aria-label="Pages"
          className="max-h-[calc(100vh-3.5rem)] overflow-y-auto border-b border-rule bg-card px-4 pb-4 sm:px-6 md:hidden"
        >
          <Link
            href="/"
            aria-current={onQuery ? "page" : undefined}
            onClick={() => setOpen(false)}
            className="mt-3 flex h-12 items-center justify-between rounded-md bg-sign px-4 text-lg font-bold text-white"
          >
            Query
            <Arrow className="h-5 w-5" />
          </Link>
          {GROUPS.map((g) => (
            <div key={g.name} className="mt-4">
              <p className="text-sm font-semibold text-ink-2">{g.name}</p>
              {g.pages.map((p) => (
                <Link
                  key={p.href}
                  href={p.href}
                  aria-current={p.href === pathname ? "page" : undefined}
                  onClick={() => setOpen(false)}
                  className="flex h-12 items-center justify-between border-b border-rule text-lg font-semibold last:border-b-0 aria-[current=page]:text-sign"
                >
                  {p.label}
                  <Arrow className="h-5 w-5" />
                </Link>
              ))}
            </div>
          ))}
        </nav>
      )}
    </header>
  );
}
