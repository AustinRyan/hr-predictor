"use client";

import { useEffect, useState } from "react";

const STATUS_MESSAGES: readonly string[] = [
  "CALIBRATING MODEL v4.2.1…",
  "LOADING STATCAST FEED…",
  "SAMPLING WIND VECTORS…",
  "PROJECTING LINEUPS…",
  "READY.",
];

/**
 * Boot radar sweep. Fills bar to 100% over ~900ms, cycles status lines,
 * then fades out. Skipped entirely on prefers-reduced-motion.
 */
function prefersReducedMotionInitial(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function BootLoader() {
  // Lazy init: if user prefers reduced motion, start already-done so the
  // radar never animates. Avoids a setState-in-effect on first render.
  const [done, setDone] = useState<boolean>(prefersReducedMotionInitial);
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState(STATUS_MESSAGES[0]);

  useEffect(() => {
    if (done) return;

    const duration = 900;
    const start = performance.now();
    let raf = 0;

    const step = (t: number): void => {
      const p = Math.min(1, (t - start) / duration);
      setProgress(p);
      const idx = Math.min(STATUS_MESSAGES.length - 1, Math.floor(p * STATUS_MESSAGES.length));
      setStatus(STATUS_MESSAGES[idx]);
      if (p < 1) {
        raf = requestAnimationFrame(step);
      } else {
        setTimeout(() => setDone(true), 280);
      }
    };

    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [done]);

  return (
    <div className={`boot ${done ? "done" : ""}`} aria-hidden={done}>
      <div className="boot-radar">
        <svg viewBox="0 0 200 200">
          <circle cx="100" cy="100" r="90" fill="none" stroke="rgba(255,90,31,.15)" strokeWidth="1" />
          <circle cx="100" cy="100" r="60" fill="none" stroke="rgba(255,90,31,.12)" strokeWidth="1" />
          <circle cx="100" cy="100" r="30" fill="none" stroke="rgba(255,90,31,.10)" strokeWidth="1" />
          <line x1="100" y1="100" x2="100" y2="10" stroke="var(--accent)" strokeWidth="2" className="boot-sweep" />
          <circle cx="100" cy="100" r="3" fill="var(--accent)" />
        </svg>
      </div>
      <div className="boot-meta">
        <div className="boot-word">HOMERUN</div>
        <div className="boot-status">{status}</div>
        <div className="boot-bar">
          <span style={{ width: `${Math.round(progress * 100)}%` }} />
        </div>
      </div>
    </div>
  );
}
