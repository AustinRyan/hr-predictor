import type { HeroStats } from "@/lib/adapters";
import { headshotUrl, type Pick } from "@/lib/pick-view";

function formatDate(): string {
  return new Date()
    .toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" })
    .toUpperCase();
}

function fmtPct(v: number | null | undefined, decimals = 1): string {
  return v === null || v === undefined ? "—" : `${(v * 100).toFixed(decimals)}`;
}
function fmtNum(v: number | null | undefined, decimals = 1): string {
  return v === null || v === undefined ? "—" : v.toFixed(decimals);
}
function fmtPark(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  const delta = v - 100;
  const sign = delta >= 0 ? "+" : "";
  return `${sign}${delta.toFixed(0)}`;
}

type Props = {
  picks?: readonly Pick[];
  topStats?: HeroStats;
  ticker?: readonly string[];
  gameCount?: number;
  modelVersion?: string;
  brier?: number | null;
};

export function Hero({ picks, topStats, ticker, gameCount, modelVersion, brier }: Props = {}) {
  const source = picks ?? [];
  const topPick = source[0];
  const tickerItems = ticker && ticker.length > 0 ? ticker : ["NO LIVE PICKS LOADED"];
  // Double the ticker so the CSS keyframe (-50%) loops seamlessly.
  const tickerLoop = [...tickerItems, ...tickerItems];
  const modelLabel = modelVersion ? modelVersion.toUpperCase() : "MODEL UNAVAILABLE";
  const brierLabel = brier != null ? `CALIBRATED TO ${brier.toFixed(4)} BRIER` : "CALIBRATION UNAVAILABLE";
  const slateLabel = gameCount != null ? `${gameCount} GAMES` : "NO SLATE";

  return (
    <section className="hero" id="top">
      <div className="hero-grid" aria-hidden="true" />

      <div className="hero-strip">
        <span>GAME DAY · {formatDate()}</span>
        <span className="strip-dot">●</span>
        <span>{modelLabel}</span>
        <span className="strip-dot">●</span>
        <span>{slateLabel}</span>
        <span className="strip-dot">●</span>
        <span>{brierLabel}</span>
      </div>

      <div className="hero-stage">
        <div className="hero-title">
          <div className="eyebrow">
            <span className="bar" />
            <span>TODAY&apos;S #1 PROJECTED HOMER</span>
          </div>
          <h1 className="display">
            <span className="line l1"><span>CALL</span></span>
            <span className="line l2"><span>YOUR</span></span>
            <span className="line l3"><span>SHOT<span className="period">.</span></span></span>
          </h1>
          <p className="hero-lede">
            Every hitter. Every pitcher. Every park. A deep-learning model that grades
            the long ball before the first pitch — and tells you <em>why</em>.
          </p>
          <div className="hero-cta">
            <a href="#app" className="btn btn-primary">
              <span>Open today&apos;s board</span>
              <span className="btn-arrow">→</span>
            </a>
            <a href="#how" className="btn btn-ghost">How it works</a>
          </div>
        </div>

        <aside className="pick-card" aria-label="Top pick">
          <div className="pick-card-head">
            <span className="pick-rank">NO. 01</span>
            <span className="pick-tag">{topPick ? "LOCK OF THE DAY" : "AWAITING DATA"}</span>
          </div>

          <div className="pick-portrait">
            <div className="pick-live">{topPick ? "PROJECTING NEXT AB…" : "NO PICKS LOADED"}</div>
            <div className="portrait-grid" />
            {topPick && (
              <div className="portrait-img">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={headshotUrl(topPick.id)} alt="" />
              </div>
            )}
            {topPick && topPick.num > 0 && <div className="portrait-number">{topPick.num}</div>}
            <div className="portrait-noise" />
          </div>

          <div className="pick-identity">
            <div className="player-name">
              <span className="pn-first">{topPick?.first ?? "TODAY'S"}</span>
              <span className="pn-last">{topPick?.last ?? "BOARD"}</span>
            </div>
            <div className="player-meta">
              <span className="team-chip">{topPick?.team ?? "LIVE"}</span>
              <span>·</span>
              <span>{topPick?.pos ?? "MODEL"}</span>
              <span>·</span>
              <span>{topPick ? `BATS ${topPick.hand}` : "REAL DATA ONLY"}</span>
            </div>
          </div>

          <div className="pick-prob">
            <div className="prob-label">P(HOME RUN)</div>
            <div className="prob-big">
              {topPick ? topPick.prob.toFixed(1) : "--"}
              {topPick && <span className="pct">%</span>}
            </div>
            <div
              className="prob-bar"
              role="progressbar"
              aria-valuenow={topPick?.prob ?? 0}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <div className="prob-bar-fill" style={{ ["--w" as string]: `${topPick?.prob ?? 0}%` }} />
              <div className="prob-bar-ticks" aria-hidden="true">
                <span style={{ ["--x" as string]: "25%" }} />
                <span style={{ ["--x" as string]: "50%" }} />
                <span style={{ ["--x" as string]: "75%" }} />
              </div>
            </div>
            <div className="prob-sub">
              {topPick ? (
                <>
                  <span>vs <b>{topPick.vs}</b></span>
                  <span>·</span>
                  <span>{topPick.park}</span>
                  <span>·</span>
                  <span>{topPick.time}</span>
                </>
              ) : (
                <span>No model output found for the current slate.</span>
              )}
            </div>
          </div>

          <div className="pick-stats">
            <div className="ps">
              <div className="ps-k">E[HR]</div>
              <div className="ps-v">{topPick ? topPick.ehr.toFixed(3) : "—"}</div>
            </div>
            <div className="ps">
              <div className="ps-k">BARREL%</div>
              <div className="ps-v">{fmtPct(topStats?.barrelPct)}</div>
            </div>
            <div className="ps">
              <div className="ps-k">EV<sub>90</sub></div>
              <div className="ps-v">{fmtNum(topStats?.p90Ev)}</div>
            </div>
            <div className="ps">
              <div className="ps-k">PARK</div>
              <div className="ps-v">{fmtPark(topStats?.parkFactor)}</div>
            </div>
          </div>
        </aside>
      </div>

      <div className="ticker" aria-hidden="true">
        <div className="ticker-track">
          {tickerLoop.map((t, i) => (
            <span className="t-item" key={i}>
              <span>{t}</span>
              <span className="t-dot">◆</span>
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}
