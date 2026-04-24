"use client";

import { useEffect, useState } from "react";

/**
 * Type H → R anywhere to launch a ball across the viewport with a giant
 * "HOME RUN" flash. Gracefully ignored under prefers-reduced-motion.
 */
export function HomerunEasterEgg() {
  const [firing, setFiring] = useState(false);

  useEffect(() => {
    const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (prefersReduced) return;

    let primed = false;
    let timer: number | undefined;

    const handler = (e: KeyboardEvent): void => {
      // Ignore repeats inside text fields (so you can still type "HR" in inputs).
      const target = e.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;

      const key = e.key.toLowerCase();
      if (key === "h") {
        primed = true;
        window.clearTimeout(timer);
        timer = window.setTimeout(() => {
          primed = false;
        }, 600);
        return;
      }
      if (key === "r" && primed) {
        primed = false;
        window.clearTimeout(timer);
        setFiring(true);
        window.setTimeout(() => setFiring(false), 1700);
      }
    };

    window.addEventListener("keydown", handler);
    return () => {
      window.removeEventListener("keydown", handler);
      window.clearTimeout(timer);
    };
  }, []);

  if (!firing) return null;

  return (
    <>
      <div className="hr-flash" aria-hidden="true" />
      <div className="hr-ball" aria-hidden="true" />
      <div className="hr-text" aria-hidden="true">HOME RUN</div>
    </>
  );
}
