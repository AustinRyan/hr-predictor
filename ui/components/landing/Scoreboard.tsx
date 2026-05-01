import type { ScoreboardGame } from "@/lib/pick-view";

type Props = { games?: readonly ScoreboardGame[] };

export function Scoreboard({ games }: Props = {}) {
  const list: readonly ScoreboardGame[] = games ?? [];
  return (
    <section className="scoreboard" id="scoreboard">
      <div className="section-head">
        <span className="section-num">/ 01</span>
        <h2 className="section-title">
          THE BOARD,<br />
          BEFORE THE <span className="accent">BOOKS</span>.
        </h2>
        <p className="section-kicker">
          While sportsbooks price on public narrative, we price on 118 features per
          matchup. The scoreboard below reads live off the production ensemble
          model.
        </p>
      </div>

      <div className="scoreboard-leds">
        {list.length === 0 ? (
          <article className="led">
            <div className="led-top">
              <span>LIVE DB</span>
              <span>EMPTY</span>
            </div>
            <div className="led-row">
              <div className="led-team">
                <div className="led-abbr">NO</div>
                <div className="led-info">
                  <div className="led-name">NO LIVE PICKS LOADED</div>
                  <div className="led-sub">run refresh picks or check Vercel database env</div>
                </div>
              </div>
            </div>
          </article>
        ) : (
          list.map((g, i) => {
            const [name, pct] = g.topProb.split(" · ");
            return (
              <article className="led" key={`${g.home}-${g.away}-${i}`}>
                <div className="led-top">
                  <span>GAME {String(i + 1).padStart(2, "0")}</span>
                  <span>{g.time} ET</span>
                </div>
                <div className="led-row">
                  <div className="led-team">
                    <div className="led-abbr">{g.away}</div>
                    <div className="led-info">
                      <div className="led-name">{g.away} AWAY</div>
                      <div className="led-sub">projected top pick</div>
                    </div>
                  </div>
                </div>
                <div className="led-row">
                  <div className="led-team">
                    <div className="led-abbr">{g.home}</div>
                    <div className="led-info">
                      <div className="led-name">{g.home} HOME</div>
                      <div className="led-sub">{name}</div>
                    </div>
                  </div>
                  <div className="led-prob">{pct}</div>
                </div>
              </article>
            );
          })
        )}
      </div>

      <div className="scoreboard-stats">
        <div className="stat">
          <div className="stat-num">118</div>
          <div className="stat-label">Features per matchup</div>
        </div>
        <div className="stat">
          <div className="stat-num">{list.length}</div>
          <div className="stat-label">Games on tonight&apos;s slate</div>
        </div>
        <div className="stat">
          <div className="stat-num">0.0434</div>
          <div className="stat-label">Brier · test set</div>
        </div>
        <div className="stat">
          <div className="stat-num">0.0064</div>
          <div className="stat-label">Calibration (ECE)</div>
        </div>
      </div>
    </section>
  );
}
