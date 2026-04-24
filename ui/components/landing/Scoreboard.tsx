import { SCOREBOARD } from "@/lib/mock-data";

export function Scoreboard() {
  return (
    <section className="scoreboard" id="scoreboard">
      <div className="section-head">
        <span className="section-num">/ 01</span>
        <h2 className="section-title">
          THE BOARD,<br />
          BEFORE THE <span className="accent">BOOKS</span>.
        </h2>
        <p className="section-kicker">
          While sportsbooks price on public narrative, we price on 1,400 features per
          plate appearance. The scoreboard below refreshes every 90 seconds off
          Statcast, weather, and bullpen state.
        </p>
      </div>

      <div className="scoreboard-leds">
        {SCOREBOARD.map((g, i) => {
          const [name, pct] = g.topProb.split(" · ");
          return (
            <article className="led" key={i}>
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
        })}
      </div>

      <div className="scoreboard-stats">
        <div className="stat">
          <div className="stat-num">1,412</div>
          <div className="stat-label">Features per at-bat</div>
        </div>
        <div className="stat">
          <div className="stat-num">7.3</div>
          <div className="stat-label">Seconds from pitch to model</div>
        </div>
        <div className="stat">
          <div className="stat-num">0.0043</div>
          <div className="stat-label">Brier score, rolling 30d</div>
        </div>
        <div className="stat">
          <div className="stat-num">162</div>
          <div className="stat-label">Games tracked · nightly</div>
        </div>
      </div>
    </section>
  );
}
