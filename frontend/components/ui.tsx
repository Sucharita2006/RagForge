import Link from "next/link";

import { Arrow, Check, Cross, Dash } from "@/components/icons";

export function PageHead({
  title,
  purpose,
  children,
}: {
  title: string;
  purpose: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-x-8 gap-y-4">
      {/* React 19 hoists this into <head>, so every page names itself. */}
      <title>{title === "Query" ? "ragforge" : `${title} · ragforge`}</title>
      <div>
        <h1 className="text-[2rem] font-bold leading-tight tracking-[-0.02em]">{title}</h1>
        <p className="mt-2 max-w-prose text-[1.0625rem] text-ink-2">{purpose}</p>
      </div>
      {children}
    </div>
  );
}

export function Section({
  title,
  note,
  children,
}: {
  title: string;
  note?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mt-12">
      <h2 className="text-xl font-bold tracking-[-0.01em]">{title}</h2>
      {note && <p className="mt-1 max-w-prose text-[0.9375rem] text-ink-2">{note}</p>}
      <div className="mt-4">{children}</div>
    </section>
  );
}

const TONES = {
  good: { box: "bg-go text-white", text: "text-go", icon: Check },
  bad: { box: "bg-stop text-white", text: "text-stop", icon: Cross },
  neutral: { box: "bg-ink-3 text-white", text: "text-ink-2", icon: Dash },
} as const;

export type Tone = keyof typeof TONES;

/** A state is always a drawn mark and a word, never a colour alone. */
export function Mark({
  tone,
  children,
}: {
  tone: Tone;
  children: React.ReactNode;
}) {
  const t = TONES[tone];
  const Icon = t.icon;
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap font-semibold ${t.text}`}>
      <span className={`inline-flex h-5 w-5 items-center justify-center rounded ${t.box}`}>
        <Icon className="h-3.5 w-3.5" />
      </span>
      {children}
    </span>
  );
}

/** What went wrong, and what to do about it. */
export function Problem({ children }: { children: React.ReactNode }) {
  return (
    <p role="alert" className="mb-6 flex max-w-prose items-start gap-3 rounded-lg bg-stop-tint p-4">
      <span className="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded bg-stop text-white">
        <Cross className="h-3.5 w-3.5" />
      </span>
      <span>{children}</span>
    </p>
  );
}

export function Empty({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="max-w-prose rounded-lg bg-card p-6">
      <h2 className="text-lg font-bold">{title}</h2>
      <div className="mt-2 space-y-3 text-ink-2">{children}</div>
    </div>
  );
}

/** A magenta sign: where the proof continues. */
export function Sign({
  href,
  title,
  detail,
}: {
  href: string;
  title: string;
  detail: string;
}) {
  return (
    <Link
      href={href}
      className="flap-in flex items-center gap-4 rounded-lg bg-sign p-3 pr-5 text-white transition-colors duration-150 hover:bg-sign-press"
    >
      <span className="inline-flex h-12 w-12 shrink-0 items-center justify-center rounded bg-white text-xl text-sign">
        <Arrow />
      </span>
      <span>
        <span className="block text-lg font-bold leading-snug">{title}</span>
        <span className="block text-[0.9375rem] text-white/85">{detail}</span>
      </span>
    </Link>
  );
}

/** The arrow a primary action carries in a leading square, as a sign does. */
export function Lead() {
  return (
    <span className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded bg-white text-ink">
      <Arrow className="h-4 w-4" />
    </span>
  );
}

/** Wide tables scroll inside their own region, reachable from the keyboard. */
export function Scroll({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div role="region" aria-label={label} tabIndex={0} className="overflow-x-auto">
      {children}
    </div>
  );
}

export function Rows({ count = 4 }: { count?: number }) {
  return (
    <div aria-hidden="true" className="space-y-3">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="skeleton h-11" />
      ))}
    </div>
  );
}

export function Code({ children }: { children: React.ReactNode }) {
  return (
    <code className="rounded bg-ground px-1.5 py-0.5 font-mono text-[0.875em] text-ink">
      {children}
    </code>
  );
}
