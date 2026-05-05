"use client";

import { useState } from "react";
import type { Pick } from "@/lib/pick-view";
import { formatBoardProbability } from "@/lib/probability-format";

type Props = {
  legs: Pick[];
  combinedP: number;
  pays: string;
  onReset: () => void;
};

function genTicketNum(): string {
  const n = Math.floor(Math.random() * 900000 + 100000);
  return `HR-${n}`;
}

function dateStamp(): string {
  return new Date().toLocaleDateString("en-US", { month: "2-digit", day: "2-digit", year: "2-digit" });
}

/**
 * Render the ticket element to a PNG. We use a hand-rolled canvas draw
 * (not html2canvas) so CSS gradients, custom fonts, and the perforated
 * edges all survive into the exported image reliably.
 */
async function renderTicketToPng(legs: Pick[], pays: string, ticketNum: string): Promise<Blob> {
  const w = 540;
  const legH = 28;
  const baseH = 520;
  const h = baseH + legs.length * legH;

  const canvas = document.createElement("canvas");
  const dpr = Math.min(window.devicePixelRatio || 1, 3);
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("canvas 2d unavailable");
  ctx.scale(dpr, dpr);

  // ticket body — cream paper gradient
  const grad = ctx.createLinearGradient(0, 0, 0, h);
  grad.addColorStop(0, "#f4e8d6");
  grad.addColorStop(1, "#e8d9bc");
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, w, h);

  // paper grain lines
  ctx.strokeStyle = "rgba(42,18,8,.04)";
  ctx.lineWidth = 1;
  for (let y = 0; y < h; y += 3) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(w, y);
    ctx.stroke();
  }

  // perforated edges
  ctx.fillStyle = "#2a1208";
  for (let x = 7; x < w; x += 14) {
    ctx.beginPath(); ctx.arc(x, 2, 2, 0, Math.PI * 2); ctx.fill();
    ctx.beginPath(); ctx.arc(x, h - 2, 2, 0, Math.PI * 2); ctx.fill();
  }

  // border
  ctx.strokeStyle = "#2a1208";
  ctx.lineWidth = 1;
  ctx.strokeRect(0.5, 6.5, w - 1, h - 13);

  const pad = 26;
  let y = 36;

  // brand
  ctx.textAlign = "center";
  ctx.fillStyle = "#c8302a";
  ctx.font = "900 36px 'Barlow Condensed', system-ui, sans-serif";
  ctx.fillText("HOMERUN", w / 2, y);
  y += 6;
  ctx.fillStyle = "rgba(42,18,8,.6)";
  ctx.font = "500 10px 'JetBrains Mono', monospace";
  ctx.fillText("CALL YOUR SHOT", w / 2, y + 12);
  y += 30;

  // dashed divider
  ctx.strokeStyle = "rgba(42,18,8,.4)";
  ctx.setLineDash([4, 4]);
  ctx.beginPath(); ctx.moveTo(pad, y); ctx.lineTo(w - pad, y); ctx.stroke();
  ctx.setLineDash([]);

  // meta row
  y += 22;
  ctx.textAlign = "left";
  ctx.fillStyle = "rgba(42,18,8,.55)";
  ctx.font = "500 9px 'JetBrains Mono', monospace";
  ctx.fillText("DATE", pad, y);
  ctx.textAlign = "right";
  ctx.fillText("TICKET #", w - pad, y);
  y += 14;
  ctx.fillStyle = "#0a0a0a";
  ctx.font = "800 15px 'Barlow Condensed', system-ui, sans-serif";
  ctx.textAlign = "left";
  ctx.fillText(dateStamp(), pad, y);
  ctx.textAlign = "right";
  ctx.fillText(ticketNum, w - pad, y);
  y += 14;

  ctx.strokeStyle = "rgba(42,18,8,.4)";
  ctx.setLineDash([4, 4]);
  ctx.beginPath(); ctx.moveTo(pad, y); ctx.lineTo(w - pad, y); ctx.stroke();
  ctx.setLineDash([]);

  // legs
  y += 18;
  ctx.font = "800 13px 'Barlow Condensed', system-ui, sans-serif";
  for (const leg of legs) {
    ctx.textAlign = "left";
    ctx.fillStyle = "#0a0a0a";
    ctx.fillText(`${leg.first} ${leg.last}`.toUpperCase(), pad, y);
    ctx.font = "500 10px 'JetBrains Mono', monospace";
    ctx.fillStyle = "rgba(42,18,8,.6)";
    ctx.fillText(`${leg.team} · VS ${leg.vs}`.toUpperCase(), pad, y + 12);
    ctx.textAlign = "right";
    ctx.font = "800 15px 'Barlow Condensed', system-ui, sans-serif";
    ctx.fillStyle = "#c8302a";
    ctx.fillText(formatBoardProbability(leg.prob), w - pad, y + 4);
    y += legH;
    ctx.font = "800 13px 'Barlow Condensed', system-ui, sans-serif";
  }

  ctx.strokeStyle = "rgba(42,18,8,.4)";
  ctx.setLineDash([4, 4]);
  ctx.beginPath(); ctx.moveTo(pad, y); ctx.lineTo(w - pad, y); ctx.stroke();
  ctx.setLineDash([]);

  // total
  y += 26;
  ctx.textAlign = "left";
  ctx.font = "500 10px 'JetBrains Mono', monospace";
  ctx.fillStyle = "rgba(42,18,8,.6)";
  ctx.fillText("$100 PAYS", pad, y);
  y += 4;
  ctx.font = "900 40px 'Barlow Condensed', system-ui, sans-serif";
  ctx.fillStyle = "#c8302a";
  ctx.fillText(pays, pad, y + 32);

  // barcode
  const bx = w - pad - 120;
  const by = y + 2;
  const bh = 38;
  const heights = [0.7, 1.0, 0.5, 0.9, 0.6, 0.8, 1.0, 0.45, 0.85, 0.65, 0.95, 0.55, 0.75, 1.0, 0.5, 0.9, 0.7, 1.0, 0.45, 0.85];
  ctx.fillStyle = "#2a1208";
  let bxi = bx;
  for (const frac of heights) {
    const wi = frac >= 0.9 ? 3 : 2;
    ctx.fillRect(bxi, by + bh * (1 - frac), wi, bh * frac);
    bxi += wi + 2;
  }

  // LOCKED stamp (rotated)
  ctx.save();
  ctx.translate(w - 70, 120);
  ctx.rotate((-14 * Math.PI) / 180);
  ctx.fillStyle = "rgba(244,232,214,.4)";
  ctx.fillRect(-44, -16, 88, 34);
  ctx.strokeStyle = "#c8302a";
  ctx.lineWidth = 3;
  ctx.strokeRect(-44, -16, 88, 34);
  ctx.fillStyle = "#c8302a";
  ctx.textAlign = "center";
  ctx.font = "900 22px 'Barlow Condensed', system-ui, sans-serif";
  ctx.fillText("LOCKED", 0, 6);
  ctx.restore();

  return new Promise<Blob>((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) resolve(blob);
      else reject(new Error("toBlob returned null"));
    }, "image/png");
  });
}

export function Ticket({ legs, combinedP, pays, onReset }: Props) {
  // Stable per-ticket values — computed once on mount via lazy init.
  const [ticketNum] = useState<string>(() => genTicketNum());
  const [date] = useState<string>(() => dateStamp());
  const [toast, setToast] = useState<{ kind: "ok" | "err"; msg: string } | null>(null);

  async function handleShare(): Promise<void> {
    try {
      const blob = await renderTicketToPng(legs, pays, ticketNum);
      const file = new File([blob], `homerun-parlay-${ticketNum}.png`, { type: "image/png" });

      const nav = navigator as Navigator & {
        canShare?: (data: { files: File[] }) => boolean;
        share?: (data: { files: File[]; title?: string; text?: string }) => Promise<void>;
      };

      if (nav.canShare?.({ files: [file] }) && nav.share) {
        await nav.share({
          files: [file],
          title: "Homerun parlay",
          text: `${legs.length} legs · ${(combinedP * 100).toFixed(2)}% · $100 pays ${pays}`,
        });
        setToast({ kind: "ok", msg: "Shared." });
      } else {
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `homerun-parlay-${ticketNum}.png`;
        a.click();
        URL.revokeObjectURL(url);
        setToast({ kind: "ok", msg: "Downloaded ticket PNG." });
      }
    } catch (err) {
      console.error(err);
      setToast({ kind: "err", msg: "Share failed." });
    }
    window.setTimeout(() => setToast(null), 2400);
  }

  return (
    <>
      <div className="ticket" id="ticket-el">
        <div className="ticket-stamp">LOCKED</div>
        <div className="ticket-brand">
          <div className="tb-logo">HOMERUN</div>
          <div className="tb-sub">CALL YOUR SHOT</div>
        </div>
        <div className="ticket-meta">
          <div className="tm-col">
            <div className="tm-k">DATE</div>
            <div className="tm-v">{date}</div>
          </div>
          <div className="tm-col">
            <div className="tm-k">TICKET #</div>
            <div className="tm-v">{ticketNum}</div>
          </div>
        </div>
        <div className="ticket-legs">
          {legs.map((l) => (
            <div className="t-leg" key={l.id}>
              <div>
                <b>{l.first} {l.last}</b>
                <div style={{ fontSize: 9, letterSpacing: ".14em", color: "rgba(42,18,8,.6)" }}>
                  {l.team} · VS {l.vs}
                </div>
              </div>
              <div className="t-leg-prob">{formatBoardProbability(l.prob)}</div>
            </div>
          ))}
        </div>
        <div className="ticket-total">
          <div>
            <div className="tt-k">$100 PAYS</div>
            <div className="tt-v">{pays}</div>
          </div>
          <div className="ticket-barcode" aria-hidden="true">
            {Array.from({ length: 20 }).map((_, i) => (
              <span key={i} style={{ height: `${[70,100,50,90,60,80,100,45,85,65,95,55,75,100,50,90,70,100,45,85][i]}%`, width: [1,2,4,7,10,14,17].includes(i) ? 3 : 2 }} />
            ))}
          </div>
        </div>
        <div className="ticket-actions">
          <button
            type="button"
            className="ticket-share"
            onClick={() => { void handleShare(); }}
            aria-label="Share ticket as image"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8" />
              <polyline points="16 6 12 2 8 6" />
              <line x1="12" y1="2" x2="12" y2="15" />
            </svg>
            SHARE
          </button>
          <button type="button" className="ticket-reset" onClick={onReset}>
            tear up ticket
          </button>
        </div>
      </div>

      {toast && (
        <div className={`share-toast show ${toast.kind === "err" ? "err" : ""}`} role="status">
          {toast.msg}
        </div>
      )}
    </>
  );
}
