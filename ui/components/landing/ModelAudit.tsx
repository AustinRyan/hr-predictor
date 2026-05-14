import Link from "next/link";

type Props = {
  modelVersion?: string | null;
  brier?: number | null;
};

function formatBrier(value?: number | null): string {
  return typeof value === "number" ? value.toFixed(3) : "PENDING";
}

export function ModelAudit({ modelVersion, brier }: Props) {
  return (
    <section className="model-audit" id="model-audit">
      <div className="model-audit-grid">
        <div className="model-audit-copy">
          <div className="handoff-eyebrow">
            <span className="bar" />
            <span>SECTION / 04 · MODEL AUDIT</span>
          </div>
          <h2 className="model-audit-title">
            TRACK THE PICKS.<br />
            <span className="accent">GRADE THE EDGE.</span>
          </h2>
          <p className="model-audit-kicker">
            Review settled top picks, full-game HR hits, market edge, and live
            calibration before the next slate locks.
          </p>
          <Link href="/model" className="btn btn-primary model-audit-btn">
            View model history <span className="btn-arrow">→</span>
          </Link>
        </div>

        <div className="model-audit-ledger" aria-label="Model audit summary">
          <div className="audit-row">
            <span>HISTORY</span>
            <b>7D TOP PICKS</b>
          </div>
          <div className="audit-row">
            <span>VERSION</span>
            <b>{modelVersion?.toUpperCase() ?? "MODEL READY"}</b>
          </div>
          <div className="audit-row">
            <span>TEST BRIER</span>
            <b>{formatBrier(brier)}</b>
          </div>
          <div className="audit-row accent">
            <span>DESTINATION</span>
            <b>/MODEL</b>
          </div>
        </div>
      </div>
    </section>
  );
}
