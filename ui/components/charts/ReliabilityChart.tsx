import type { ReliabilityBin } from "@/lib/types";

type Props = {
  bins: readonly ReliabilityBin[];
  // Axis max in probability space. Default 0.3 (our data never exceeds ~0.12).
  maxP?: number;
};

/**
 * SVG reliability chart (no external lib).
 * X = predicted probability bin midpoint. Y = observed HR rate.
 * Perfect calibration is the 45° diagonal; points above diagonal = over-
 * confident, below = under-confident.
 */
export function ReliabilityChart({ bins, maxP = 0.3 }: Props) {
  const w = 600;
  const h = 360;
  const pad = { top: 20, right: 20, bottom: 44, left: 52 };
  const innerW = w - pad.left - pad.right;
  const innerH = h - pad.top - pad.bottom;

  const xScale = (p: number): number => pad.left + (p / maxP) * innerW;
  const yScale = (p: number): number => pad.top + innerH - (p / maxP) * innerH;

  // Filter bins with data (mean_pred + actual_rate both non-null).
  const usable = bins.filter(
    (b): b is ReliabilityBin & { mean_pred: number; actual_rate: number } =>
      b.mean_pred !== null && b.actual_rate !== null && b.count > 0,
  );

  const ticks = [0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3].filter((t) => t <= maxP);

  return (
    <div className="reliability-wrap">
      <svg viewBox={`0 0 ${w} ${h}`} role="img" aria-label="Reliability diagram">
        {/* axes */}
        <line x1={pad.left} y1={pad.top} x2={pad.left} y2={h - pad.bottom} stroke="var(--line)" />
        <line x1={pad.left} y1={h - pad.bottom} x2={w - pad.right} y2={h - pad.bottom} stroke="var(--line)" />

        {/* grid + tick labels */}
        {ticks.map((t) => (
          <g key={`tx-${t}`}>
            <line x1={xScale(t)} y1={pad.top} x2={xScale(t)} y2={h - pad.bottom}
              stroke="rgba(255,255,255,.04)" />
            <text x={xScale(t)} y={h - pad.bottom + 16} fontSize="10"
              fill="var(--ink-mute)" textAnchor="middle"
              style={{ fontFamily: "var(--f-mono)", letterSpacing: ".08em" }}>
              {(t * 100).toFixed(0)}%
            </text>
          </g>
        ))}
        {ticks.map((t) => (
          <g key={`ty-${t}`}>
            <line x1={pad.left} y1={yScale(t)} x2={w - pad.right} y2={yScale(t)}
              stroke="rgba(255,255,255,.04)" />
            <text x={pad.left - 8} y={yScale(t) + 4} fontSize="10"
              fill="var(--ink-mute)" textAnchor="end"
              style={{ fontFamily: "var(--f-mono)", letterSpacing: ".08em" }}>
              {(t * 100).toFixed(0)}%
            </text>
          </g>
        ))}

        {/* perfect-calibration diagonal */}
        <line
          x1={xScale(0)} y1={yScale(0)}
          x2={xScale(maxP)} y2={yScale(maxP)}
          stroke="var(--ink-mute)" strokeDasharray="4 6" strokeWidth="1"
        />

        {/* reliability line */}
        {usable.length > 1 && (
          <polyline
            points={usable.map((b) => `${xScale(b.mean_pred)},${yScale(b.actual_rate)}`).join(" ")}
            fill="none"
            stroke="var(--accent)"
            strokeWidth="2"
          />
        )}
        {/* reliability points — radius scales gently with bin count */}
        {usable.map((b, i) => {
          const r = Math.max(3, Math.min(12, Math.sqrt(b.count) / 2));
          return (
            <circle
              key={i}
              cx={xScale(b.mean_pred)}
              cy={yScale(b.actual_rate)}
              r={r}
              fill="var(--accent)"
              stroke="#0a0a0a"
              strokeWidth="1.5"
            />
          );
        })}

        {/* axis labels */}
        <text
          x={pad.left + innerW / 2} y={h - 6} fontSize="10"
          fill="var(--ink-dim)" textAnchor="middle"
          style={{ fontFamily: "var(--f-mono)", letterSpacing: ".22em", textTransform: "uppercase" }}
        >
          PREDICTED P(HR)
        </text>
        <text
          x={14} y={pad.top + innerH / 2} fontSize="10"
          fill="var(--ink-dim)" textAnchor="middle"
          transform={`rotate(-90 14 ${pad.top + innerH / 2})`}
          style={{ fontFamily: "var(--f-mono)", letterSpacing: ".22em", textTransform: "uppercase" }}
        >
          OBSERVED RATE
        </text>
      </svg>
    </div>
  );
}
