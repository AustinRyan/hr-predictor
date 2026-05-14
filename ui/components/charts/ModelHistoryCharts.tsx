import {
  buildCumulativeUnits,
  buildDailyExpectedActual,
  buildRankBandCalibration,
  type CumulativeUnitsPoint,
  type DailyExpectedActualPoint,
  type RankBandCalibrationPoint,
} from "@/lib/model-history-charts";
import type { PickHistoryItem } from "@/lib/types";
import type { ReactNode } from "react";

type Props = {
  items: readonly PickHistoryItem[];
};

type Scale = (value: number) => number;

function ChartShell({
  title,
  kicker,
  children,
}: {
  title: string;
  kicker: string;
  children: ReactNode;
}) {
  return (
    <article className="history-chart-card">
      <div className="history-chart-copy">
        <div className="detail-card-k">{title}</div>
        <p>{kicker}</p>
      </div>
      {children}
    </article>
  );
}

function formatUnits(value: number): string {
  const sign = value >= 0 ? "+" : "";
  return `${sign}${value.toFixed(1)}u`;
}

function shortDate(value: string): string {
  const [, month, day] = value.split("-");
  return `${month}/${day}`;
}

function niceCeil(value: number): number {
  if (value <= 1) return 1;
  return Math.ceil(value);
}

function rangeScale(min: number, max: number, start: number, end: number): Scale {
  const span = max - min || 1;
  return (value: number) => start + ((value - min) / span) * (end - start);
}

function EmptyChart({ label }: { label: string }) {
  return (
    <div className="history-chart-empty">
      <span>{label}</span>
    </div>
  );
}

function ExpectedActualChart({ points }: { points: readonly DailyExpectedActualPoint[] }) {
  if (points.length === 0) return <EmptyChart label="No settled pick history yet" />;

  const w = 720;
  const h = 340;
  const pad = { top: 24, right: 28, bottom: 58, left: 56 };
  const innerW = w - pad.left - pad.right;
  const innerH = h - pad.top - pad.bottom;
  const yMax = niceCeil(
    Math.max(...points.flatMap((point) => [point.expectedHits, point.actualHits])),
  );
  const y = rangeScale(0, yMax, h - pad.bottom, pad.top);
  const groupW = innerW / points.length;
  const barW = Math.max(12, Math.min(34, groupW * 0.24));
  const ticks = Array.from({ length: yMax + 1 }, (_, i) => i);

  return (
    <svg viewBox={`0 0 ${w} ${h}`} role="img" aria-label="Expected versus actual home runs by day">
      {ticks.map((tick) => (
        <g key={tick}>
          <line x1={pad.left} y1={y(tick)} x2={w - pad.right} y2={y(tick)} stroke="rgba(255,255,255,.05)" />
          <text x={pad.left - 10} y={y(tick) + 4} textAnchor="end" className="chart-axis-text">
            {tick}
          </text>
        </g>
      ))}
      <line x1={pad.left} y1={pad.top} x2={pad.left} y2={h - pad.bottom} stroke="var(--line)" />
      <line x1={pad.left} y1={h - pad.bottom} x2={w - pad.right} y2={h - pad.bottom} stroke="var(--line)" />

      {points.map((point, index) => {
        const cx = pad.left + groupW * index + groupW / 2;
        const expectedH = h - pad.bottom - y(point.expectedHits);
        const actualH = h - pad.bottom - y(point.actualHits);
        return (
          <g key={point.date}>
            <rect
              x={cx - barW - 2}
              y={y(point.expectedHits)}
              width={barW}
              height={expectedH}
              fill="rgba(255,255,255,.22)"
            />
            <rect
              x={cx + 2}
              y={y(point.actualHits)}
              width={barW}
              height={actualH}
              fill="var(--accent)"
            />
            <text x={cx} y={h - pad.bottom + 18} textAnchor="middle" className="chart-axis-text">
              {shortDate(point.date)}
            </text>
            <text x={cx} y={h - pad.bottom + 34} textAnchor="middle" className="chart-axis-text muted">
              {point.picks} picks
            </text>
          </g>
        );
      })}

      <g transform={`translate(${pad.left}, 14)`}>
        <rect width="10" height="10" fill="rgba(255,255,255,.22)" />
        <text x="18" y="9" className="chart-axis-text">Expected</text>
        <rect x="102" width="10" height="10" fill="var(--accent)" />
        <text x="120" y="9" className="chart-axis-text">Actual</text>
      </g>
      <text x="18" y={pad.top + innerH / 2} textAnchor="middle" className="chart-axis-label" transform={`rotate(-90 18 ${pad.top + innerH / 2})`}>
        HR PICKS
      </text>
    </svg>
  );
}

function CumulativeUnitsChart({ points }: { points: readonly CumulativeUnitsPoint[] }) {
  if (points.length === 0) return <EmptyChart label="No saved sportsbook odds for this window" />;

  const w = 720;
  const h = 340;
  const pad = { top: 28, right: 32, bottom: 54, left: 62 };
  const innerW = w - pad.left - pad.right;
  const values = points.map((point) => point.cumulativeUnits);
  const minY = Math.floor(Math.min(0, ...values));
  const maxY = Math.ceil(Math.max(0, ...values));
  const y = rangeScale(minY, maxY, h - pad.bottom, pad.top);
  const x = (index: number) =>
    points.length === 1
      ? pad.left + innerW / 2
      : pad.left + (index / (points.length - 1)) * innerW;
  const coords = points.map((point, index) => `${x(index)},${y(point.cumulativeUnits)}`).join(" ");
  const ticks = [minY, 0, maxY].filter((tick, index, arr) => arr.indexOf(tick) === index);

  return (
    <svg viewBox={`0 0 ${w} ${h}`} role="img" aria-label="Cumulative flat betting units">
      {ticks.map((tick) => (
        <g key={tick}>
          <line
            x1={pad.left}
            y1={y(tick)}
            x2={w - pad.right}
            y2={y(tick)}
            stroke={tick === 0 ? "rgba(255,255,255,.22)" : "rgba(255,255,255,.05)"}
            strokeDasharray={tick === 0 ? "4 6" : undefined}
          />
          <text x={pad.left - 10} y={y(tick) + 4} textAnchor="end" className="chart-axis-text">
            {formatUnits(tick)}
          </text>
        </g>
      ))}
      <polyline points={coords} fill="none" stroke="var(--accent)" strokeWidth="2.5" />
      {points.map((point, index) => (
        <g key={`${point.label}-${index}`}>
          <circle
            cx={x(index)}
            cy={y(point.cumulativeUnits)}
            r={point.units >= 0 ? 5 : 4}
            fill={point.units >= 0 ? "var(--accent)" : "var(--warn)"}
            stroke="#0a0a0a"
            strokeWidth="1.5"
          />
          {(index === 0 || index === points.length - 1) && (
            <text x={x(index)} y={h - pad.bottom + 20} textAnchor="middle" className="chart-axis-text">
              {shortDate(point.date)}
            </text>
          )}
        </g>
      ))}
      <text x={pad.left + innerW / 2} y={h - 8} textAnchor="middle" className="chart-axis-label">
        SETTLED PICKS WITH ODDS
      </text>
      <text x={w - pad.right} y={pad.top - 10} textAnchor="end" className="chart-value-label">
        {formatUnits(points[points.length - 1]!.cumulativeUnits)}
      </text>
    </svg>
  );
}

function RankBandChart({ points }: { points: readonly RankBandCalibrationPoint[] }) {
  const populated = points.filter((point) => point.count > 0);
  if (populated.length === 0) return <EmptyChart label="No ranked settled picks yet" />;

  const w = 720;
  const h = 340;
  const pad = { top: 28, right: 28, bottom: 62, left: 56 };
  const innerW = w - pad.left - pad.right;
  const y = rangeScale(0, 1, h - pad.bottom, pad.top);
  const groupW = innerW / points.length;
  const barW = Math.max(18, Math.min(42, groupW * 0.22));
  const ticks = [0, 0.25, 0.5, 0.75, 1];

  return (
    <svg viewBox={`0 0 ${w} ${h}`} role="img" aria-label="Hit rate by model rank band">
      {ticks.map((tick) => (
        <g key={tick}>
          <line x1={pad.left} y1={y(tick)} x2={w - pad.right} y2={y(tick)} stroke="rgba(255,255,255,.05)" />
          <text x={pad.left - 10} y={y(tick) + 4} textAnchor="end" className="chart-axis-text">
            {(tick * 100).toFixed(0)}%
          </text>
        </g>
      ))}
      <line x1={pad.left} y1={pad.top} x2={pad.left} y2={h - pad.bottom} stroke="var(--line)" />
      <line x1={pad.left} y1={h - pad.bottom} x2={w - pad.right} y2={h - pad.bottom} stroke="var(--line)" />
      {points.map((point, index) => {
        const cx = pad.left + groupW * index + groupW / 2;
        return (
          <g key={point.label}>
            <rect
              x={cx - barW - 3}
              y={y(point.expectedRate)}
              width={barW}
              height={h - pad.bottom - y(point.expectedRate)}
              fill="rgba(255,255,255,.22)"
            />
            <rect
              x={cx + 3}
              y={y(point.actualRate)}
              width={barW}
              height={h - pad.bottom - y(point.actualRate)}
              fill="var(--accent)"
            />
            <text x={cx} y={h - pad.bottom + 20} textAnchor="middle" className="chart-axis-text">
              {point.label}
            </text>
            <text x={cx} y={h - pad.bottom + 38} textAnchor="middle" className="chart-axis-text muted">
              n={point.count}
            </text>
          </g>
        );
      })}
      <g transform={`translate(${pad.left}, 14)`}>
        <rect width="10" height="10" fill="rgba(255,255,255,.22)" />
        <text x="18" y="9" className="chart-axis-text">Expected rate</text>
        <rect x="132" width="10" height="10" fill="var(--accent)" />
        <text x="150" y="9" className="chart-axis-text">Actual rate</text>
      </g>
    </svg>
  );
}

export function ModelHistoryCharts({ items }: Props) {
  const daily = buildDailyExpectedActual(items);
  const units = buildCumulativeUnits(items);
  const rankBands = buildRankBandCalibration(items);

  return (
    <section className="history-chart-grid" aria-label="Top pick history charts">
      <ChartShell
        title="EXPECTED VS ACTUAL"
        kicker="Each date compares the model's summed HR probability for the top picks against how many of those picks actually homered."
      >
        <ExpectedActualChart points={daily} />
      </ChartShell>

      <ChartShell
        title="CUMULATIVE UNITS"
        kicker="Flat one-unit result for settled picks that had real saved sportsbook odds. Missing odds are excluded from this line."
      >
        <CumulativeUnitsChart points={units} />
      </ChartShell>

      <ChartShell
        title="RANK BAND HIT RATE"
        kicker="Rank bands show whether the top of the board is separating from the rest: expected hit rate versus actual hit rate."
      >
        <RankBandChart points={rankBands} />
      </ChartShell>
    </section>
  );
}
