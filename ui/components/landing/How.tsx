export function How() {
  return (
    <section className="how" id="how">
      <div className="section-head">
        <span className="section-num">/ 03</span>
        <h2 className="section-title">
          WE DON&apos;T GUESS.<br />
          <span className="accent">WE GRADE</span>.
        </h2>
      </div>

      <div className="how-steps">
        <article className="step">
          <div className="step-num">01</div>
          <h3>INGEST</h3>
          <p>
            Statcast pitch-by-pitch, park telemetry, lineup projections, bullpen
            state, and NOAA wind at 20-meter resolution.
          </p>
          <ul className="step-list">
            <li><span>STATCAST</span><span>pitch × spin × zone</span></li>
            <li><span>WEATHER</span><span>wind · temp · humidity</span></li>
            <li><span>PARK</span><span>30 stadium profiles</span></li>
            <li><span>LINEUP</span><span>projected PA count</span></li>
          </ul>
        </article>

        <article className="step">
          <div className="step-num">02</div>
          <h3>MODEL</h3>
          <p>
            A gradient-boosted ensemble estimates per-PA HR probability, conditioned
            on pitcher arsenal and park microclimate. Calibrated nightly.
          </p>
          <ul className="step-list">
            <li><span>ARCH</span><span>XGB + LightGBM</span></li>
            <li><span>FEATURES</span><span>118 per matchup</span></li>
            <li><span>CALIB</span><span>isotonic, nightly</span></li>
            <li><span>HOLDOUT</span><span>2025 full season</span></li>
          </ul>
        </article>

        <article className="step">
          <div className="step-num">03</div>
          <h3>GRADE</h3>
          <p>
            Aggregate across projected plate appearances to a game-level probability.
            Rank the slate. Surface the edges.
          </p>
          <ul className="step-list">
            <li><span>OUTPUT</span><span>P(≥1 HR), E[HR]</span></li>
            <li><span>EXPLAIN</span><span>top-10 SHAP</span></li>
            <li><span>REFRESH</span><span>every 90s</span></li>
            <li><span>VERSION</span><span>semver + audit</span></li>
          </ul>
        </article>
      </div>
    </section>
  );
}
