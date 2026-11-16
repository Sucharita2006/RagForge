const NBSP = " "; // a number never wraps away from its unit

/** 820 ms, 8.2 s, 2 min 38 s: the unit a person would say. */
export function duration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}${NBSP}ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)}${NBSP}s`;
  const total = Math.round(s);
  return `${Math.floor(total / 60)}${NBSP}min${NBSP}${total % 60}${NBSP}s`;
}

export function clock(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

export function when(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function percent(fraction: number): string {
  return `${Math.round(fraction * 100)}%`;
}

/** Hosted calls cost fractions of a cent; self-hosted ones cost exactly nothing. */
export function money(usd: number): string {
  return usd === 0 ? "$0" : `$${usd.toFixed(usd < 0.01 ? 6 : 2)}`;
}

export function fixed(n: number | null | undefined, digits = 3): string {
  return n === null || n === undefined ? "–" : n.toFixed(digits);
}

/** Three decimals for a score, whole numbers for a large quantity such as milliseconds. */
export function measure(n: number): string {
  return Math.abs(n) >= 100 ? Math.round(n).toLocaleString("en") : n.toFixed(3);
}

export function signed(n: number, digits?: number): string {
  const body = digits === undefined ? measure(Math.abs(n)) : Math.abs(n).toFixed(digits);
  return `${n >= 0 ? "+" : "−"}${body}`;
}
