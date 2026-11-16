"use client";

import { useState } from "react";

import { Empty, Mark, PageHead, Problem, Rows, Scroll, Section, Sign } from "@/components/ui";
import { message, send, useApi } from "@/lib/api";
import { percent } from "@/lib/format";

interface CalibrationPoint {
  threshold: number;
  coverage: number;
  answered_precision: number;
}

interface SettingsData {
  abstain_threshold: number;
  confidence_weights: Record<string, number>;
  minicheck_support_threshold: number;
  calibration_curve: CalibrationPoint[] | null;
}

const WEIGHT_NAMES: Record<string, string> = {
  claim_support: "Claim support",
  retrieval: "Retrieval strength",
  retrieval_strength: "Retrieval strength",
  sufficiency: "Citation coverage",
};

/** Coverage and answered-precision against the threshold, with the slider's
 *  position marked. Lines are SVG stretched to the plot; every label is HTML,
 *  so text keeps its size at any width. The two lines differ in dash as well
 *  as in colour. */
function Curve({ points, at }: { points: CalibrationPoint[]; at: number }) {
  const line = (pick: (p: CalibrationPoint) => number) =>
    points
      .map((p, i) => `${i ? "L" : "M"}${(p.threshold * 100).toFixed(2)} ${((1 - pick(p)) * 100).toFixed(2)}`)
      .join(" ");

  return (
    <figure className="max-w-3xl">
      <div
        role="img"
        aria-label="Coverage and answered-precision at each abstain threshold"
        className="relative ml-12 mr-4 h-56 sm:h-64"
      >
        {[1, 0.5, 0].map((v) => (
          <div
            key={v}
            className="absolute inset-x-0 border-t border-rule"
            style={{ top: `${(1 - v) * 100}%` }}
          >
            <span className="absolute -left-12 w-10 -translate-y-1/2 text-right text-sm tabular-nums text-ink-2">
              {percent(v)}
            </span>
          </div>
        ))}
        <svg
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          aria-hidden="true"
          className="absolute inset-0 h-full w-full overflow-visible"
        >
          <path
            d={line((p) => p.coverage)}
            fill="none"
            strokeWidth={2.5}
            vectorEffect="non-scaling-stroke"
            className="stroke-ink"
          />
          <path
            d={line((p) => p.answered_precision)}
            fill="none"
            strokeWidth={2.5}
            strokeDasharray="7 4"
            vectorEffect="non-scaling-stroke"
            className="stroke-ink-3"
          />
        </svg>
        <div className="absolute inset-y-0 w-0.5 -translate-x-1/2 bg-ink" style={{ left: `${at * 100}%` }}>
          <span className="absolute -top-2.5 left-1/2 h-2.5 w-2.5 -translate-x-1/2 bg-ink" />
        </div>
      </div>
      <div className="relative ml-12 mr-4 mt-2 h-5 text-sm tabular-nums text-ink-2" aria-hidden="true">
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <span
            key={t}
            className="absolute -translate-x-1/2 first:translate-x-0 last:-translate-x-full"
            style={{ left: `${t * 100}%` }}
          >
            {t.toFixed(2)}
          </span>
        ))}
      </div>
      <figcaption className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-[0.9375rem]">
        <span className="flex items-center gap-2">
          <span className="h-0.5 w-6 shrink-0 bg-ink" />
          Coverage: questions that get an answer
        </span>
        <span className="flex items-center gap-2">
          <span className="w-6 shrink-0 border-t-2 border-dashed border-ink-3" />
          Answered-precision: answers that should have been given
        </span>
      </figcaption>
    </figure>
  );
}

export default function TrustSettings() {
  const loaded = useApi<SettingsData>("/settings");
  const data = loaded.data;
  // `saved` is what a successful PATCH returned; `draft` is the slider before saving.
  const [saved, setSaved] = useState<number | null>(null);
  const [draft, setDraft] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const error = saveError ?? loaded.error;

  const live = saved ?? data?.abstain_threshold ?? 0;
  const value = draft ?? live;
  const changed = Math.abs(value - live) > 1e-9;

  async function save() {
    setSaving(true);
    setSaveError(null);
    try {
      const next = await send<SettingsData>(
        "/settings/abstain-threshold",
        { threshold: value },
        "PATCH",
      );
      setSaved(next.abstain_threshold);
      setDraft(null);
    } catch (err) {
      setSaveError(message(err));
    } finally {
      setSaving(false);
    }
  }

  const curve = data?.calibration_curve ?? null;
  const nearest =
    curve?.reduce((closest, point) =>
      Math.abs(point.threshold - value) < Math.abs(closest.threshold - value) ? point : closest,
    ) ?? null;

  return (
    <>
      <PageHead
        title="Trust settings"
        purpose="One number decides whether an answer is shown. Raise the threshold and fewer questions are answered, but more of the answers are right."
      />

      {error && <Problem>{error}</Problem>}
      {!data && !error && <Rows />}

      {data && (
        <>
          <div className="grid gap-6 lg:grid-cols-12">
            <div className="self-start rounded-xl bg-panel p-6 text-white lg:col-span-4">
              <p className="text-[5.5rem] font-extrabold leading-none tracking-[-0.03em] tabular-nums">
                {value.toFixed(2)}
              </p>
              <p className="mt-3 text-lg font-bold">Abstain threshold</p>
              <p className="mt-1 text-[0.9375rem] text-white/75">
                An answer with confidence under this is withheld.
              </p>
              {nearest && (
                <dl className="mt-6 space-y-1 border-t border-white/20 pt-4 text-[0.9375rem]">
                  <div className="flex justify-between gap-4">
                    <dt className="text-white/75">Coverage here</dt>
                    <dd className="font-semibold tabular-nums">{percent(nearest.coverage)}</dd>
                  </div>
                  <div className="flex justify-between gap-4">
                    <dt className="text-white/75">Answered-precision here</dt>
                    <dd className="font-semibold tabular-nums">
                      {percent(nearest.answered_precision)}
                    </dd>
                  </div>
                </dl>
              )}
            </div>

            <div className="lg:col-span-8">
              <label htmlFor="threshold" className="label">
                Threshold, from 0 to 1
              </label>
              <input
                id="threshold"
                type="range"
                min={0}
                max={1}
                step={0.01}
                value={value}
                onChange={(e) => setDraft(Number(e.target.value))}
                className="h-11 w-full max-w-3xl"
              />
              <div className="mt-2 flex flex-wrap items-center gap-4">
                <button
                  type="button"
                  onClick={save}
                  disabled={saving || !changed}
                  className="btn btn-primary"
                >
                  {saving ? "Saving" : "Save threshold"}
                </button>
                {changed ? (
                  <span className="text-[0.9375rem] text-ink-2">
                    Not saved. The live value is {live.toFixed(2)}.
                  </span>
                ) : (
                  <Mark tone="good">Live</Mark>
                )}
              </div>

              <div className="mt-8">
                {curve ? (
                  <Curve points={curve} at={value} />
                ) : (
                  <Empty title="No calibration run yet">
                    <p>
                      Calibration sweeps the threshold over a held-out set and records what each
                      value would have answered. Run it once to draw the curve here:
                    </p>
                    <pre className="overflow-x-auto rounded-md bg-ground p-3 font-mono text-sm text-ink">
                      docker compose exec api python scripts/calibrate_abstain_threshold.py
                    </pre>
                  </Empty>
                )}
              </div>
            </div>
          </div>

          <Section
            title="How confidence is built"
            note="Confidence is a weighted sum of three signals. A sentence counts as supported when its entailment score reaches the support threshold."
          >
            <dl className="max-w-md divide-y divide-rule border-y border-rule">
              {Object.entries(data.confidence_weights).map(([key, weight]) => (
                <div key={key} className="flex justify-between gap-4 py-2.5">
                  <dt>{WEIGHT_NAMES[key] ?? key}</dt>
                  <dd className="font-semibold tabular-nums">{weight}</dd>
                </div>
              ))}
              <div className="flex justify-between gap-4 py-2.5">
                <dt>Support threshold</dt>
                <dd className="font-semibold tabular-nums">{data.minicheck_support_threshold}</dd>
              </div>
            </dl>
          </Section>

          {curve && (
            <Section title="The curve as numbers">
              <Scroll label="Calibration curve">
                <table className="data max-w-md min-w-[22rem]">
                  <thead>
                    <tr>
                      <th>Threshold</th>
                      <th className="num">Coverage</th>
                      <th className="num">Answered-precision</th>
                    </tr>
                  </thead>
                  <tbody>
                    {curve
                      .filter((_, i) => i % 10 === 0)
                      .map((point) => (
                        <tr key={point.threshold}>
                          <td>{point.threshold.toFixed(2)}</td>
                          <td className="num">{percent(point.coverage)}</td>
                          <td className="num">{percent(point.answered_precision)}</td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </Scroll>
            </Section>
          )}

          <div className="mt-12 max-w-xl">
            <Sign
              href="/golden-set"
              title="See what the threshold does on the golden set"
              detail="Runs report how often answers were right and how often unanswerable questions were withheld"
            />
          </div>
        </>
      )}
    </>
  );
}
