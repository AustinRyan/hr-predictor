import { notFound } from "next/navigation";
import Link from "next/link";
import { Nav } from "@/components/landing/Nav";
import { Footer } from "@/components/landing/Footer";
import { ModelHistoryCharts } from "@/components/charts/ModelHistoryCharts";
import { ReliabilityChart } from "@/components/charts/ReliabilityChart";
import { HistoryTable } from "@/components/model/HistoryTable";
import { getModelMetrics, getPickHistory } from "@/lib/api";

export const dynamic = "force-dynamic";

function nullish(v: number | null, decimals = 4): string {
  return v === null ? "—" : v.toFixed(decimals);
}

function pct(v: number | null, decimals = 1): string {
  return v === null ? "—" : `${(v * 100).toFixed(decimals)}%`;
}

function units(v: number | null): string {
  if (v === null) return "—";
  const sign = v >= 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}u`;
}

export default async function ModelPage() {
  const data = await getModelMetrics();
  if (!data) notFound();

  const { training_metadata: meta, training_metrics: metrics, rolling_live: live } = data;
  const history = await getPickHistory(meta.model_version, 7, 20);

  return (
    <>
      <Nav />
      <main className="detail">
        <Link href="/" className="back-link">← Back to board</Link>

        <header style={{ maxWidth: 1400, marginBottom: 60, paddingBottom: 40, borderBottom: "1px solid var(--line)" }}>
          <span className="section-num">/ MODEL</span>
          <h1 className="detail-title">
            PRODUCTION MODEL<br />
            <span style={{ color: "var(--accent)" }}>{meta.model_version}</span>
          </h1>
          <div className="detail-sub" style={{ marginTop: 16 }}>
            <span>FEATURES <b>{meta.num_features}</b></span>
            <span>·</span>
            <span>TRAINING <b>{meta.training_range[0]}</b> → <b>{meta.training_range[1]}</b></span>
            {meta.git_sha && (<>
              <span>·</span>
              <span>GIT <b>{meta.git_sha.slice(0, 8)}</b></span>
            </>)}
          </div>
        </header>

        <h2 className="section-num" style={{ marginBottom: 12 }}>/ TRAINING METRICS</h2>
        <div className="detail-grid" style={{ marginBottom: 60 }}>
          <div className="detail-card">
            <div className="detail-card-k">TEST LOG LOSS</div>
            <div className="detail-card-v accent">{nullish(metrics.test_log_loss, 5)}</div>
            <div className="detail-card-sub">lower is better</div>
          </div>
          <div className="detail-card">
            <div className="detail-card-k">TEST BRIER</div>
            <div className="detail-card-v">{nullish(metrics.test_brier, 5)}</div>
            <div className="detail-card-sub">base-rate floor ≈ .0443</div>
          </div>
          <div className="detail-card">
            <div className="detail-card-k">TEST ECE</div>
            <div className="detail-card-v">{nullish(metrics.test_ece, 5)}</div>
            <div className="detail-card-sub">expected calibration error</div>
          </div>
          <div className="detail-card">
            <div className="detail-card-k">TEST AUC</div>
            <div className="detail-card-v">{nullish(metrics.test_auc, 4)}</div>
          </div>
          <div className="detail-card">
            <div className="detail-card-k">PRECISION @ TOP-20</div>
            <div className="detail-card-v">{nullish(metrics.test_precision_at_top_k, 4)}</div>
          </div>
          <div className="detail-card">
            <div className="detail-card-k">VAL LOG LOSS</div>
            <div className="detail-card-v">{nullish(metrics.val_log_loss, 5)}</div>
          </div>
        </div>

        <h2 className="section-num" style={{ marginBottom: 12 }}>/ RELIABILITY</h2>
        {live.reliability.length > 0 ? (
          <ReliabilityChart bins={live.reliability} />
        ) : (
          <div className="detail-card" style={{ marginBottom: 24 }}>
            <div className="detail-card-k">NO OUTCOMES KNOWN YET</div>
            <div className="detail-card-v small">
              Today is day 1 of live predictions; the reliability diagram populates as HR outcomes
              land over the coming days.
            </div>
          </div>
        )}

        <h2 className="section-num" style={{ marginTop: 48, marginBottom: 12 }}>
          / ROLLING · {live.window_days}D
        </h2>
        <div className="detail-grid">
          <div className="detail-card">
            <div className="detail-card-k">PREDICTIONS</div>
            <div className="detail-card-v">{live.n_predictions}</div>
            <div className="detail-card-sub">evaluated with known outcomes</div>
          </div>
          <div className="detail-card">
            <div className="detail-card-k">LIVE LOG LOSS</div>
            <div className="detail-card-v">{nullish(live.log_loss, 5)}</div>
          </div>
          <div className="detail-card">
            <div className="detail-card-k">LIVE BRIER</div>
            <div className="detail-card-v">{nullish(live.brier, 5)}</div>
          </div>
          <div className="detail-card">
            <div className="detail-card-k">LIVE ECE</div>
            <div className="detail-card-v">{nullish(live.ece, 5)}</div>
          </div>
          <div className="detail-card">
            <div className="detail-card-k">FROM</div>
            <div className="detail-card-v small">{live.evaluated_from ?? "—"}</div>
          </div>
          <div className="detail-card">
            <div className="detail-card-k">TO</div>
            <div className="detail-card-v small">{live.evaluated_to ?? "—"}</div>
          </div>
        </div>

        <h2 className="section-num" style={{ marginTop: 48, marginBottom: 12 }}>
          / TOP PICK HISTORY · 7D
        </h2>
        {history && history.items.length > 0 ? (
          <>
            <div className="detail-grid" style={{ marginBottom: 24 }}>
              <div className="detail-card">
                <div className="detail-card-k">TOP PICKS</div>
                <div className="detail-card-v">{history.summary.picks}</div>
                <div className="detail-card-sub">top 20 per settled day</div>
              </div>
              <div className="detail-card">
                <div className="detail-card-k">HITS</div>
                <div className="detail-card-v accent">{history.summary.hits}</div>
                <div className="detail-card-sub">{pct(history.summary.hit_rate)} hit rate</div>
              </div>
              <div className="detail-card">
                <div className="detail-card-k">EXPECTED HITS</div>
                <div className="detail-card-v">{history.summary.expected_hits.toFixed(2)}</div>
                <div className="detail-card-sub">sum of model probabilities</div>
              </div>
              <div className="detail-card">
                <div className="detail-card-k">FLAT BET RESULT</div>
                <div className="detail-card-v">{units(history.summary.settled_profit_units)}</div>
                <div className="detail-card-sub">
                  {history.summary.picks_with_odds} picks had saved odds
                </div>
              </div>
            </div>
            <ModelHistoryCharts items={history.items} />
            <HistoryTable items={history.items} />
          </>
        ) : (
          <div className="detail-card">
            <div className="detail-card-k">NO SETTLED TOP PICKS YET</div>
            <div className="detail-card-v small">
              This fills after predictions and next-day Statcast results exist for the same model version.
            </div>
          </div>
        )}
      </main>
      <Footer />
    </>
  );
}
