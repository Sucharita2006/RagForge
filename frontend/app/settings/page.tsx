"use client";

import { useCallback, useEffect, useState } from "react";

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

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function Settings() {
  const [data, setData] = useState<SettingsData | null>(null);
  const [sliderValue, setSliderValue] = useState(0.55);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchSettings = useCallback(async () => {
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/settings`);
      if (!res.ok) throw new Error(`Request failed: ${res.status}`);
      const settings = (await res.json()) as SettingsData;
      setData(settings);
      setSliderValue(settings.abstain_threshold);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    }
  }, []);

  useEffect(() => {
    // fetch-on-mount with no data-fetching library in this project yet;
    // eslint-plugin-react-hooks' cascading-render warning doesn't apply here
    // since there's only ever one render pass for this initial load.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchSettings();
  }, [fetchSettings]);

  async function saveThreshold() {
    setSaving(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/settings/abstain-threshold`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ threshold: sliderValue }),
      });
      if (!res.ok) throw new Error(`Request failed: ${res.status}`);
      setData((await res.json()) as SettingsData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setSaving(false);
    }
  }

  const nearestCalibrationPoint =
    data?.calibration_curve?.reduce((closest, point) =>
      Math.abs(point.threshold - sliderValue) < Math.abs(closest.threshold - sliderValue)
        ? point
        : closest,
    ) ?? null;

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold">Settings</h1>
        <p className="text-sm text-neutral-500">
          Trust-layer configuration (SPEC.md §8.5) — the abstain threshold trades answer coverage
          against answered-precision.
        </p>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {data && (
        <>
          <div className="flex flex-col gap-3 rounded border border-neutral-200 p-4 dark:border-neutral-800">
            <div className="flex items-center justify-between">
              <label htmlFor="threshold" className="text-sm font-medium">
                Abstain threshold: {sliderValue.toFixed(2)}
              </label>
              <button
                onClick={saveThreshold}
                disabled={saving}
                className="rounded bg-neutral-900 px-3 py-1 text-xs text-white disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900"
              >
                {saving ? "Saving..." : "Save"}
              </button>
            </div>
            <input
              id="threshold"
              type="range"
              min={0}
              max={1}
              step={0.01}
              value={sliderValue}
              onChange={(e) => setSliderValue(Number(e.target.value))}
              className="w-full"
            />
            {nearestCalibrationPoint && (
              <p className="text-xs text-neutral-500">
                At this threshold (calibrated curve): coverage{" "}
                {(nearestCalibrationPoint.coverage * 100).toFixed(0)}%, answered-precision{" "}
                {(nearestCalibrationPoint.answered_precision * 100).toFixed(0)}%
              </p>
            )}
          </div>

          <div className="rounded border border-neutral-200 p-4 text-sm dark:border-neutral-800">
            <h2 className="mb-2 font-medium">Confidence weights</h2>
            <ul className="flex flex-col gap-1 text-neutral-500">
              {Object.entries(data.confidence_weights).map(([key, value]) => (
                <li key={key}>
                  {key}: {value}
                </li>
              ))}
              <li>minicheck_support_threshold: {data.minicheck_support_threshold}</li>
            </ul>
          </div>

          {data.calibration_curve ? (
            <div className="overflow-x-auto">
              <h2 className="mb-2 text-sm font-medium">Calibration curve</h2>
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr className="border-b border-neutral-300 text-left dark:border-neutral-700">
                    <th className="p-2">Threshold</th>
                    <th className="p-2 text-right">Coverage</th>
                    <th className="p-2 text-right">Answered-precision</th>
                  </tr>
                </thead>
                <tbody>
                  {data.calibration_curve
                    .filter((_, i) => i % 10 === 0)
                    .map((point) => (
                      <tr
                        key={point.threshold}
                        className="border-b border-neutral-100 dark:border-neutral-900"
                      >
                        <td className="p-2 tabular-nums">{point.threshold.toFixed(2)}</td>
                        <td className="p-2 text-right tabular-nums">
                          {(point.coverage * 100).toFixed(0)}%
                        </td>
                        <td className="p-2 text-right tabular-nums">
                          {(point.answered_precision * 100).toFixed(0)}%
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-neutral-500">
              No calibration run yet — run{" "}
              <code>scripts/calibrate_abstain_threshold.py</code> to fit one against
              calibration.jsonl.
            </p>
          )}
        </>
      )}
    </main>
  );
}
