// 0–100 risk bar for ScrutinyReport.riskScore / QueueItem.riskScore (contract
// integers). Bands per ui-guidelines §3: low <30, medium 30–59, high >=60
// (60 = SPEC §7 eval flag threshold, so UI and eval agree).

export type RiskBand = "low" | "medium" | "high";

const BAND_META: Record<RiskBand, { bar: string; text: string; label: string }> = {
  low: { bar: "bg-emerald-500", text: "text-emerald-700", label: "Low risk" },
  medium: { bar: "bg-amber-500", text: "text-amber-700", label: "Medium risk" },
  high: { bar: "bg-red-500", text: "text-red-700", label: "High risk" },
};

export function riskBand(score: number): RiskBand {
  if (score >= 60) return "high";
  if (score >= 30) return "medium";
  return "low";
}

export function RiskMeter({
  score,
  showLabel = false,
}: {
  score: number;
  showLabel?: boolean;
}) {
  const clamped = Math.max(0, Math.min(100, Math.round(score)));
  const band = riskBand(clamped);
  const meta = BAND_META[band];
  return (
    <div className="flex items-center gap-2">
      <div
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={clamped}
        aria-label={`Risk score ${clamped} of 100 (${meta.label})`}
        className="h-2 w-24 shrink-0 overflow-hidden rounded-full bg-zinc-100"
      >
        <div
          className={`h-full rounded-full ${meta.bar}`}
          style={{ width: `${clamped}%` }}
        />
      </div>
      <span className={`w-7 text-right font-mono text-sm font-semibold ${meta.text}`}>
        {clamped}
      </span>
      {showLabel && (
        <span className={`text-xs font-medium ${meta.text}`}>{meta.label}</span>
      )}
    </div>
  );
}
