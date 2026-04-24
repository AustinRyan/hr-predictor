"use client";

import { useEffect, useState } from "react";

type ChyronState = { inning: string; label: string };

const SECTION_MAP: readonly { selector: string; inning: string; label: string }[] = [
  { selector: "#slate", inning: "TOP OF 1ST", label: "TONIGHT'S SLATE" },
  { selector: "#scoreboard", inning: "TOP OF 2ND", label: "LIVE BOARD" },
  { selector: "#arc", inning: "TOP OF 3RD", label: "MODEL · ARC" },
  { selector: "#how", inning: "TOP OF 4TH", label: "METHOD" },
  { selector: "#app", inning: "TOP OF 5TH", label: "LAUNCH" },
];

/**
 * A fixed-position inning ticker that slides in from the left whenever
 * the viewport enters a new section. Hidden in reduced-motion.
 */
export function Chyron() {
  const [visible, setVisible] = useState(false);
  const [state, setState] = useState<ChyronState>({ inning: "TOP OF 1ST", label: "LANDING" });

  useEffect(() => {
    const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (prefersReduced) return;

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          const match = SECTION_MAP.find((s) => entry.target.matches(s.selector));
          if (!match) continue;
          setState({ inning: match.inning, label: match.label });
          setVisible(true);
          window.clearTimeout((observer as unknown as { _hideT?: number })._hideT);
          const hideT = window.setTimeout(() => setVisible(false), 2400);
          (observer as unknown as { _hideT?: number })._hideT = hideT;
        }
      },
      { threshold: 0.35 },
    );

    for (const s of SECTION_MAP) {
      const el = document.querySelector(s.selector);
      if (el) observer.observe(el);
    }

    return () => {
      observer.disconnect();
    };
  }, []);

  return (
    <div
      className="chyron"
      aria-hidden="true"
      style={{
        position: "fixed",
        top: 72,
        left: 0,
        zIndex: 49,
        background: "var(--accent)",
        color: "#0a0a0a",
        fontFamily: "var(--f-display)",
        fontWeight: 800,
        fontSize: 12,
        letterSpacing: ".18em",
        textTransform: "uppercase",
        padding: "8px 16px",
        display: "flex",
        gap: 10,
        alignItems: "center",
        transform: visible ? "translateX(0)" : "translateX(-110%)",
        transition: "transform .5s cubic-bezier(.7,0,.2,1)",
      }}
    >
      <span style={{ fontSize: 10 }}>▸</span>
      <span>{state.inning}</span>
      <span style={{ opacity: 0.5 }}>/</span>
      <span>{state.label}</span>
    </div>
  );
}
