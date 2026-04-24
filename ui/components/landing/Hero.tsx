import { PICKS, TICKER, headshotUrl, type Pick } from "@/lib/mock-data";

function formatDate(): string {
  return new Date()
    .toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" })
    .toUpperCase();
}

type Props = {
  picks?: readonly Pick[];
};

export function Hero({ picks }: Props = {}) {
  const source = picks ?? PICKS;
  const topPick = source[0] ?? PICKS[0];
  // Double the ticker so the CSS keyframe (-50%) loops seamlessly.
  const tickerLoop = [...TICKER, ...TICKER];

  return (
    <section className="hero" id="top">
      <div className="hero-grid" aria-hidden="true" />

      <div className="hero-strip">
        <span>GAME DAY · {formatDate()}</span>
        <span className="strip-dot">●</span>
        <span>MODEL v4.2.1</span>
        <span className="strip-dot">●</span>
        <span>15 SLATE</span>
        <span className="strip-dot">●</span>
        <span>CALIBRATED TO .0043 BRIER</span>
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
            <span className="pick-tag">LOCK OF THE DAY</span>
          </div>

          <div className="pick-portrait">
            <div className="pick-live">PROJECTING NEXT AB…</div>
            <div className="portrait-grid" />
            <div className="portrait-img">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={headshotUrl(topPick.id)} alt="" />
            </div>
            <div className="portrait-number">{topPick.num}</div>
            <div className="portrait-noise" />
          </div>

          <div className="pick-identity">
            <div className="player-name">
              <span className="pn-first">{topPick.first}</span>
              <span className="pn-last">{topPick.last}</span>
            </div>
            <div className="player-meta">
              <span className="team-chip">{topPick.team}</span>
              <span>·</span>
              <span>{topPick.pos}</span>
              <span>·</span>
              <span>{topPick.hand} / R</span>
            </div>
          </div>

          <div className="pick-prob">
            <div className="prob-label">P(HOME RUN)</div>
            <div className="prob-big">
              {topPick.prob.toFixed(1)}
              <span className="pct">%</span>
            </div>
            <div
              className="prob-bar"
              role="progressbar"
              aria-valuenow={topPick.prob}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <div className="prob-bar-fill" style={{ ["--w" as string]: `${topPick.prob}%` }} />
              <div className="prob-bar-ticks" aria-hidden="true">
                <span style={{ ["--x" as string]: "25%" }} />
                <span style={{ ["--x" as string]: "50%" }} />
                <span style={{ ["--x" as string]: "75%" }} />
              </div>
            </div>
            <div className="prob-sub">
              <span>vs <b>{topPick.vs}</b></span>
              <span>·</span>
              <span>{topPick.park}</span>
              <span>·</span>
              <span>{topPick.time}</span>
            </div>
          </div>

          <div className="pick-stats">
            <div className="ps">
              <div className="ps-k">E[HR]</div>
              <div className="ps-v">{topPick.ehr.toFixed(3)}</div>
            </div>
            <div className="ps">
              <div className="ps-k">BARREL%</div>
              <div className="ps-v">22.4</div>
            </div>
            <div className="ps">
              <div className="ps-k">EV<sub>90</sub></div>
              <div className="ps-v">108.3</div>
            </div>
            <div className="ps">
              <div className="ps-k">PARK</div>
              <div className="ps-v">+6%</div>
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
