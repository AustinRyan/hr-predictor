import type { FeatureContribution } from "@/lib/types";

type Props = {
  features: readonly FeatureContribution[];
  max?: number;
};

/**
 * Top-N SHAP feature contributions, rendered as labeled bars.
 * Positive contributions use accent; negative use warn.
 * Widths scale to the largest |contribution| in the list.
 */
export function ShapBars({ features, max }: Props) {
  if (features.length === 0) {
    return (
      <div style={{
        fontFamily: "var(--f-mono)", fontSize: 11, letterSpacing: ".18em",
        color: "var(--ink-mute)", textTransform: "uppercase", padding: 16,
      }}>
        NO FEATURE CONTRIBUTIONS AVAILABLE
      </div>
    );
  }
  const trimmed = features.slice(0, max ?? 10);
  const maxAbs = Math.max(...trimmed.map((f) => Math.abs(f.contribution)));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {trimmed.map((f) => {
        const pct = maxAbs > 0 ? (Math.abs(f.contribution) / maxAbs) * 100 : 0;
        const pos = f.contribution >= 0;
        return (
          <div
            key={f.name}
            style={{
              display: "grid",
              gridTemplateColumns: "minmax(0, 1.6fr) minmax(0, 2fr) 56px",
              gap: 14,
              alignItems: "center",
            }}
          >
            <div
              style={{
                fontFamily: "var(--f-mono)",
                fontSize: 11,
                letterSpacing: ".12em",
                color: "var(--ink-dim)",
                textTransform: "uppercase",
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
              title={f.name}
            >
              {f.name}
            </div>
            <div style={{ height: 14, background: "rgba(255,255,255,.04)", position: "relative" }}>
              <span
                style={{
                  display: "block",
                  height: "100%",
                  width: `${pct}%`,
                  background: pos
                    ? "linear-gradient(90deg, var(--accent-deep), var(--accent))"
                    : "linear-gradient(90deg, var(--warn), rgba(212,62,42,.4))",
                }}
              />
            </div>
            <div
              style={{
                fontFamily: "var(--f-mono)",
                fontSize: 12,
                letterSpacing: ".04em",
                color: pos ? "var(--accent)" : "var(--warn)",
                fontVariantNumeric: "tabular-nums",
                textAlign: "right",
              }}
            >
              {f.contribution >= 0 ? "+" : ""}
              {f.contribution.toFixed(3)}
            </div>
          </div>
        );
      })}
    </div>
  );
}
