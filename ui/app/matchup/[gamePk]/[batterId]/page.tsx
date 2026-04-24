import { notFound } from "next/navigation";
import Link from "next/link";
import { Nav } from "@/components/landing/Nav";
import { Footer } from "@/components/landing/Footer";
import { ShapBars } from "@/components/charts/ShapBars";
import { getMatchup } from "@/lib/api";

export const revalidate = 120;

function pctOrDash(v: number | null | undefined, decimals = 1): string {
  return v === null || v === undefined ? "—" : `${(v * 100).toFixed(decimals)}%`;
}

function numOrDash(v: number | null | undefined, decimals = 1): string {
  return v === null || v === undefined ? "—" : v.toFixed(decimals);
}

type PageProps = { params: Promise<{ gamePk: string; batterId: string }> };

export default async function MatchupPage({ params }: PageProps) {
  const { gamePk, batterId } = await params;
  const gpk = Number.parseInt(gamePk, 10);
  const bid = Number.parseInt(batterId, 10);
  if (!Number.isFinite(gpk) || !Number.isFinite(bid)) notFound();

  const data = await getMatchup(gpk, bid);
  if (!data) notFound();

  const { game, batter, pitcher, park, weather, prediction } = data;

  return (
    <>
      <Nav />
      <main className="detail">
        <Link href="/" className="back-link">← Back to board</Link>

        <header style={{ maxWidth: 1400, marginBottom: 60 }}>
          <div className="detail-sub" style={{ marginBottom: 16 }}>
            <span>GAME <b>#{game.game_pk}</b></span>
            <span>·</span>
            <span><b>{game.away_team_abbr ?? "—"}</b> @ <b>{game.home_team_abbr ?? "—"}</b></span>
            <span>·</span>
            <span><b>{game.game_date}</b></span>
          </div>
          <h1 className="detail-title">
            {(batter.full_name ?? "—").toUpperCase()}<br />
            <span style={{ color: "var(--ink-dim)", fontSize: ".55em" }}>VS</span>
            <br />
            <span style={{ color: "var(--accent)" }}>
              {(pitcher.full_name ?? "—").toUpperCase()}
            </span>
          </h1>
          {park.park_name && (
            <div className="detail-sub" style={{ marginTop: 16 }}>
              <span>@ <b>{park.park_name.toUpperCase()}</b></span>
              {park.elevation_ft !== null && (<>
                <span>·</span>
                <span>ELEV <b>{park.elevation_ft} FT</b></span>
              </>)}
              {park.roof_type && (<>
                <span>·</span>
                <span>ROOF <b>{park.roof_type.toUpperCase()}</b></span>
              </>)}
            </div>
          )}
        </header>

        {prediction && (
          <div className="detail-grid" style={{ marginBottom: 48 }}>
            <div className="detail-card">
              <div className="detail-card-k">P(≥1 HR)</div>
              <div className="detail-card-v accent">
                {prediction.prob_at_least_one_hr === null
                  ? "—"
                  : (prediction.prob_at_least_one_hr * 100).toFixed(1)}
                <span style={{ fontSize: ".4em", color: "var(--ink-dim)", marginLeft: 4 }}>%</span>
              </div>
            </div>
            <div className="detail-card">
              <div className="detail-card-k">P(≥2 HR)</div>
              <div className="detail-card-v">
                {prediction.prob_at_least_two_hr === null
                  ? "—"
                  : (prediction.prob_at_least_two_hr * 100).toFixed(2)}
                <span style={{ fontSize: ".4em", color: "var(--ink-dim)", marginLeft: 4 }}>%</span>
              </div>
            </div>
            <div className="detail-card">
              <div className="detail-card-k">E[HR]</div>
              <div className="detail-card-v">
                {prediction.expected_hrs === null ? "—" : prediction.expected_hrs.toFixed(3)}
              </div>
            </div>
            <div className="detail-card">
              <div className="detail-card-k">MODEL</div>
              <div className="detail-card-v small">{prediction.model_version ?? "—"}</div>
              {prediction.starter_raw_prob !== null && (
                <div className="detail-card-sub">
                  raw {(prediction.starter_raw_prob * 100).toFixed(2)}% →
                  cal {prediction.starter_calibrated_prob === null ? "—" : (prediction.starter_calibrated_prob * 100).toFixed(2)}%
                </div>
              )}
            </div>
          </div>
        )}

        {prediction && prediction.top_contributing_features.length > 0 && (
          <section style={{ marginBottom: 60 }}>
            <h2 className="section-num" style={{ marginBottom: 24 }}>/ TOP 10 SHAP</h2>
            <ShapBars features={prediction.top_contributing_features} max={10} />
          </section>
        )}

        <h2 className="section-num" style={{ marginBottom: 4 }}>/ BATTER</h2>
        <div style={{
          fontFamily: "var(--f-mono)", fontSize: 10, letterSpacing: ".14em",
          color: "var(--ink-mute)", textTransform: "uppercase", marginBottom: 18,
          maxWidth: 720,
        }}>
          Season stats are the exact values the model used as input for this
          prediction — cumulative through the day before {game.game_date}.
          Formulas match Baseball Savant (barrel% = barrels / BBE, p90 EV =
          90th-pctl exit velo of batted balls). Savant shows live data; our
          values are frozen at inference time.
        </div>
        <div className="detail-grid" style={{ marginBottom: 48 }}>
          <div className="detail-card">
            <div className="detail-card-k">BARREL % · SEASON</div>
            <div className="detail-card-v">{pctOrDash(batter.b_barrel_pct_season)}</div>
          </div>
          <div className="detail-card">
            <div className="detail-card-k">AVG EV</div>
            <div className="detail-card-v">{numOrDash(batter.b_avg_ev_season)}</div>
          </div>
          <div className="detail-card">
            <div className="detail-card-k">90TH-PCT EV</div>
            <div className="detail-card-v">{numOrDash(batter.b_p90_ev_season)}</div>
          </div>
          <div className="detail-card">
            <div className="detail-card-k">HR / PA</div>
            <div className="detail-card-v">{pctOrDash(batter.b_hr_per_pa_season, 2)}</div>
          </div>
          <div className="detail-card">
            <div className="detail-card-k">vs RHP</div>
            <div className="detail-card-v">{pctOrDash(batter.b_vs_rhp_hr_per_pa_reg, 2)}</div>
          </div>
          <div className="detail-card">
            <div className="detail-card-k">vs LHP</div>
            <div className="detail-card-v">{pctOrDash(batter.b_vs_lhp_hr_per_pa_reg, 2)}</div>
          </div>
        </div>

        <h2 className="section-num" style={{ marginBottom: 12 }}>/ PITCHER</h2>
        <div className="detail-grid" style={{ marginBottom: 48 }}>
          <div className="detail-card">
            <div className="detail-card-k">HR / 9</div>
            <div className="detail-card-v">{numOrDash(pitcher.p_hr_per_9_season, 2)}</div>
          </div>
          <div className="detail-card">
            <div className="detail-card-k">BARREL % ALLOWED</div>
            <div className="detail-card-v">{pctOrDash(pitcher.p_barrel_pct_allowed_season)}</div>
          </div>
          <div className="detail-card">
            <div className="detail-card-k">FF VELO</div>
            <div className="detail-card-v">{numOrDash(pitcher.p_ff_velo_avg)}</div>
            <div className="detail-card-sub">mph avg</div>
          </div>
          <div className="detail-card">
            <div className="detail-card-k">PRIMARY PITCH</div>
            <div className="detail-card-v small">{pitcher.p_primary_pitch ?? "—"}</div>
          </div>
          <div className="detail-card">
            <div className="detail-card-k">vs RHB HR</div>
            <div className="detail-card-v">{pctOrDash(pitcher.p_vs_rhb_hr_rate, 2)}</div>
          </div>
          <div className="detail-card">
            <div className="detail-card-k">vs LHB HR</div>
            <div className="detail-card-v">{pctOrDash(pitcher.p_vs_lhb_hr_rate, 2)}</div>
          </div>
        </div>

        <h2 className="section-num" style={{ marginBottom: 12 }}>/ CONTEXT</h2>
        <div className="detail-grid">
          <div className="detail-card">
            <div className="detail-card-k">PARK FACTOR</div>
            <div className="detail-card-v accent small">
              {park.park_hr_factor_hand === null ? "—" : park.park_hr_factor_hand.toFixed(0)}
            </div>
            <div className="detail-card-sub">hand-adjusted · today</div>
          </div>
          <div className="detail-card">
            <div className="detail-card-k">TEMP</div>
            <div className="detail-card-v small">
              {weather.temperature_f === null ? "—" : `${weather.temperature_f.toFixed(0)}°F`}
            </div>
          </div>
          <div className="detail-card">
            <div className="detail-card-k">WIND</div>
            <div className="detail-card-v small">
              {weather.wind_speed_mph === null
                ? "—"
                : `${weather.wind_speed_mph.toFixed(1)} MPH`}
            </div>
            {weather.wind_direction_deg !== null && (
              <div className="detail-card-sub">
                {weather.wind_direction_deg.toFixed(0)}°
              </div>
            )}
          </div>
          <div className="detail-card">
            <div className="detail-card-k">ROOF</div>
            <div className="detail-card-v small">
              {weather.is_roof_closed === null ? (park.roof_type ?? "—") : weather.is_roof_closed ? "CLOSED" : "OPEN"}
            </div>
          </div>
          <div className="detail-card">
            <div className="detail-card-k">LINEUP SLOT</div>
            <div className="detail-card-v">{game.ctx_batting_order ?? "—"}</div>
          </div>
          <div className="detail-card">
            <div className="detail-card-k">PROJ PA</div>
            <div className="detail-card-v">{numOrDash(game.ctx_projected_pa)}</div>
          </div>
        </div>
      </main>
      <Footer />
    </>
  );
}
