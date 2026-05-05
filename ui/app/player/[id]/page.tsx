import { notFound } from "next/navigation";
import Link from "next/link";
import { Nav } from "@/components/landing/Nav";
import { Footer } from "@/components/landing/Footer";
import { getPlayer } from "@/lib/api";
import { formatModelProbability } from "@/lib/probability-format";

export const revalidate = 300;

function pctOrDash(v: number | null, decimals = 1): string {
  return v === null ? "—" : `${(v * 100).toFixed(decimals)}%`;
}

function numOrDash(v: number | null, decimals = 1): string {
  return v === null ? "—" : v.toFixed(decimals);
}

function headshot(id: number): string {
  return `https://img.mlbstatic.com/mlb-photos/image/upload/w_426,q_auto/v1/people/${id}/headshot/67/current`;
}

type PageProps = { params: Promise<{ id: string }> };

export default async function PlayerPage({ params }: PageProps) {
  const { id } = await params;
  const mlbamId = Number.parseInt(id, 10);
  if (!Number.isFinite(mlbamId)) notFound();

  const data = await getPlayer(mlbamId);
  if (!data) notFound();

  const { profile, rolling, today_prediction: pred } = data;

  return (
    <>
      <Nav />
      <main className="detail">
        <Link href="/" className="back-link">← Back to board</Link>

        <header className="detail-head">
          <div className="detail-portrait">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={headshot(profile.mlbam_id)} alt="" />
          </div>
          <div>
            <h1 className="detail-title">
              {(profile.first_name ?? "").toUpperCase()}<br />
              <span style={{ color: "var(--accent)" }}>
                {(profile.last_name ?? profile.full_name ?? "—").toUpperCase()}
              </span>
            </h1>
            <div className="detail-sub">
              <span>MLBAM <b>#{profile.mlbam_id}</b></span>
              <span>·</span>
              <span>POS <b>{profile.primary_position ?? "—"}</b></span>
              <span>·</span>
              <span>BATS <b>{profile.bats ?? "—"}</b></span>
              <span>·</span>
              <span>THROWS <b>{profile.throws ?? "—"}</b></span>
              {rolling.as_of && (<>
                <span>·</span>
                <span>AS OF <b>{rolling.as_of}</b></span>
              </>)}
            </div>
          </div>
        </header>

        {pred && (
          <>
            <h2 className="section-num" style={{ marginBottom: 12 }}>/ TONIGHT</h2>
            <div className="detail-grid" style={{ marginBottom: 48 }}>
              <div className="detail-card">
                <div className="detail-card-k">P(≥1 HR)</div>
                <div className="detail-card-v accent">
                  {formatModelProbability(pred.prob_at_least_one_hr).replace("%", "")}
                  <span style={{ fontSize: ".4em", color: "var(--ink-dim)", marginLeft: 4 }}>%</span>
                </div>
                <div className="detail-card-sub">MODEL {pred.model_version}</div>
              </div>
              <div className="detail-card">
                <div className="detail-card-k">E[HR]</div>
                <div className="detail-card-v">{pred.expected_hrs === null ? "—" : pred.expected_hrs.toFixed(3)}</div>
                <div className="detail-card-sub">expected home runs</div>
              </div>
              <div className="detail-card">
                <div className="detail-card-k">PROJECTED PA</div>
                <div className="detail-card-v">{pred.projected_pas === null ? "—" : pred.projected_pas.toFixed(1)}</div>
                <div className="detail-card-sub">projected plate appearances</div>
              </div>
              <div className="detail-card">
                <div className="detail-card-k">GAME</div>
                <div className="detail-card-v small">#{pred.game_pk}</div>
                <div className="detail-card-sub">
                  <Link href={`/matchup/${pred.game_pk}/${profile.mlbam_id}`} style={{ color: "var(--accent)" }}>
                    view matchup →
                  </Link>
                </div>
              </div>
            </div>
          </>
        )}

        <h2 className="section-num" style={{ marginBottom: 12 }}>/ ROLLING · 30D</h2>
        <div className="detail-grid">
          <div className="detail-card">
            <div className="detail-card-k">BARREL %</div>
            <div className="detail-card-v">{pctOrDash(rolling.b_barrel_pct_30d)}</div>
          </div>
          <div className="detail-card">
            <div className="detail-card-k">HARD-HIT %</div>
            <div className="detail-card-v">{pctOrDash(rolling.b_hardhit_pct_30d)}</div>
          </div>
          <div className="detail-card">
            <div className="detail-card-k">AVG EV</div>
            <div className="detail-card-v">{numOrDash(rolling.b_avg_ev_30d)}</div>
            <div className="detail-card-sub">mph</div>
          </div>
          <div className="detail-card">
            <div className="detail-card-k">90TH-PCT EV</div>
            <div className="detail-card-v">{numOrDash(rolling.b_p90_ev_30d)}</div>
            <div className="detail-card-sub">mph</div>
          </div>
          <div className="detail-card">
            <div className="detail-card-k">AVG LA</div>
            <div className="detail-card-v">{numOrDash(rolling.b_avg_la_30d)}</div>
            <div className="detail-card-sub">degrees</div>
          </div>
          <div className="detail-card">
            <div className="detail-card-k">PULLED FB %</div>
            <div className="detail-card-v">{pctOrDash(rolling.b_pulled_fb_pct_30d)}</div>
          </div>
          <div className="detail-card">
            <div className="detail-card-k">xwOBAcon</div>
            <div className="detail-card-v">{numOrDash(rolling.b_xwobacon_30d, 3)}</div>
          </div>
          <div className="detail-card">
            <div className="detail-card-k">HR / PA</div>
            <div className="detail-card-v">{pctOrDash(rolling.b_hr_per_pa_30d, 2)}</div>
          </div>
          <div className="detail-card">
            <div className="detail-card-k">PA</div>
            <div className="detail-card-v">{rolling.b_pa_count_30d ?? "—"}</div>
            <div className="detail-card-sub">last 30 days</div>
          </div>
        </div>

        <h2 className="section-num" style={{ marginTop: 48, marginBottom: 12 }}>/ SEASON</h2>
        <div className="detail-grid" style={{ marginBottom: 48 }}>
          <div className="detail-card">
            <div className="detail-card-k">BARREL %</div>
            <div className="detail-card-v">{pctOrDash(rolling.b_barrel_pct_season)}</div>
          </div>
          <div className="detail-card">
            <div className="detail-card-k">HR / PA</div>
            <div className="detail-card-v">{pctOrDash(rolling.b_hr_per_pa_season, 2)}</div>
          </div>
          <div className="detail-card">
            <div className="detail-card-k">PA</div>
            <div className="detail-card-v">{rolling.b_pa_count_season ?? "—"}</div>
          </div>
        </div>
      </main>
      <Footer />
    </>
  );
}
