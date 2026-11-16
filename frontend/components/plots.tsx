import type { Tone } from "@/components/ui";

const FILL: Record<Tone, string> = { good: "bg-go", bad: "bg-stop", neutral: "bg-ink-3" };

/** A mean with its 95% interval on a fixed 0 to 1 scale. */
export function Interval({ mean, low, high }: { mean: number; low: number; high: number }) {
  const at = (v: number) => `${Math.min(1, Math.max(0, v)) * 100}%`;
  return (
    <div className="relative h-6" aria-hidden="true">
      <div className="absolute inset-x-0 top-1/2 h-px bg-rule" />
      <div className="absolute left-0 top-1 h-4 w-px bg-ink-3" />
      <div className="absolute right-0 top-1 h-4 w-px bg-ink-3" />
      <div
        className="absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-ink"
        style={{ left: at(low), width: `calc(${at(high)} - ${at(low)})` }}
      />
      <div
        className="absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-ground bg-ink"
        style={{ left: at(mean) }}
      />
    </div>
  );
}

/** A difference with its 95% interval against a zero line. The row's own
 *  largest bound sets the scale, since metrics differ by orders of magnitude. */
export function Forest({
  delta,
  low,
  high,
  tone,
}: {
  delta: number;
  low: number;
  high: number;
  tone: Tone;
}) {
  const reach = Math.max(Math.abs(low), Math.abs(high), Math.abs(delta)) * 1.15 || 1;
  const at = (v: number) => `${50 + (v / reach) * 50}%`;
  return (
    <div className="relative h-6 min-w-[9rem]" aria-hidden="true">
      <div className="absolute inset-x-0 top-1/2 h-px bg-rule" />
      <div className="absolute left-1/2 top-0 h-6 w-0.5 -translate-x-1/2 bg-ink" />
      <div
        className={`absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full ${FILL[tone]}`}
        style={{ left: at(low), width: `calc(${at(high)} - ${at(low)})` }}
      />
      <div
        className={`absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-ground ${FILL[tone]}`}
        style={{ left: at(delta) }}
      />
    </div>
  );
}
