"use client";

import { useEffect, useRef } from "react";

type DamageEvent = { at: number; k: string; v: string };
const DAMAGE_DATA: readonly DamageEvent[] = [
  { at: 0.08, k: "EXIT VELOCITY", v: "108.3 MPH" },
  { at: 0.24, k: "LAUNCH ANGLE", v: "28.4°" },
  { at: 0.44, k: "WIND VECTOR", v: "↗ 11 MPH" },
  { at: 0.62, k: "PARK FACTOR", v: "+6%" },
  { at: 0.80, k: "CARRY", v: "+1.4 MPH" },
] as const;

const TRAIL_LEN = 10;
const SVG_NS = "http://www.w3.org/2000/svg";

function clamp(v: number, a: number, b: number): number {
  return Math.max(a, Math.min(b, v));
}

/**
 * Remap linear scroll p → time t. Real trajectories spend ~60% of flight
 * time in the upper half. Slow near apex (p ≈ 0.5), accelerate on descent.
 */
function physicsWarp(p: number): number {
  if (p < 0.5) {
    const t = p * 2;
    return 0.5 * (1 - Math.pow(1 - t, 2.2));
  }
  const t = (p - 0.5) * 2;
  return 0.5 + 0.5 * Math.pow(t, 1.6);
}

export function Arc() {
  const stageRef = useRef<HTMLDivElement | null>(null);
  const pathRef = useRef<SVGPathElement | null>(null);
  const ballRef = useRef<SVGGElement | null>(null);
  const shadowRef = useRef<SVGEllipseElement | null>(null);
  const trailRef = useRef<SVGGElement | null>(null);
  const damageRef = useRef<SVGGElement | null>(null);
  const blurStdRef = useRef<SVGFEGaussianBlurElement | null>(null);
  const streakGRef = useRef<SVGGElement | null>(null);
  const streakLineRef = useRef<SVGLineElement | null>(null);
  const batterRef = useRef<HTMLDivElement | null>(null);
  const contactFlashRef = useRef<HTMLDivElement | null>(null);
  const crowdRef = useRef<HTMLDivElement | null>(null);
  const lightsRef = useRef<HTMLDivElement | null>(null);
  const finaleRef = useRef<HTMLDivElement | null>(null);
  const finaleValRef = useRef<HTMLSpanElement | null>(null);

  useEffect(() => {
    const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (prefersReduced) return;

    const stage = stageRef.current;
    const path = pathRef.current;
    const ball = ballRef.current;
    const shadow = shadowRef.current;
    const trail = trailRef.current;
    const damageLayer = damageRef.current;
    const blurStd = blurStdRef.current;
    const streakG = streakGRef.current;
    const streakLine = streakLineRef.current;
    const batter = batterRef.current;
    const contactFlash = contactFlashRef.current;
    const crowd = crowdRef.current;
    const lights = lightsRef.current;
    const finale = finaleRef.current;
    const finaleVal = finaleValRef.current;

    if (!stage || !path || !ball || !shadow || !trail || !damageLayer || !blurStd ||
        !streakG || !streakLine || !batter || !contactFlash || !crowd || !lights ||
        !finale || !finaleVal) {
      return;
    }

    const totalLen = path.getTotalLength();
    const pathLen = 1000;

    type TrailPt = { x: number; y: number };
    const trailBuf: TrailPt[] = [];
    const damageFired = new Array(DAMAGE_DATA.length).fill(false);
    let swingFired = false;
    let finaleFired = false;
    let prevPt = path.getPointAtLength(0);
    let lastProgress = 0;

    const spawnDamage = (x: number, y: number, k: string, v: string): void => {
      const g = document.createElementNS(SVG_NS, "g");
      g.setAttribute("class", "damage");
      g.setAttribute("transform", `translate(${x},${y})`);
      g.innerHTML = `<text class="d-k" y="-22">${k}</text><text class="d-v" y="0">${v}</text>`;
      damageLayer.appendChild(g);
      window.setTimeout(() => {
        if (g.parentNode) g.parentNode.removeChild(g);
      }, 2400);
    };

    const updateTrail = (pt: TrailPt): void => {
      trailBuf.unshift({ x: pt.x, y: pt.y });
      if (trailBuf.length > TRAIL_LEN) trailBuf.length = TRAIL_LEN;
      trail.innerHTML = trailBuf
        .slice(1)
        .map((t, i) => {
          const age = (i + 1) / TRAIL_LEN;
          const r = 18 * (1 - age * 0.7);
          const op = (1 - age) * 0.45;
          return `<circle class="trail-dot" cx="${t.x}" cy="${t.y}" r="${r}" opacity="${op}"/>`;
        })
        .join("");
    };

    const fireSwing = (): void => {
      if (swingFired) return;
      swingFired = true;
      batter.classList.add("show", "swung");
      contactFlash.classList.add("fire");
      window.setTimeout(() => contactFlash.classList.remove("fire"), 500);
    };

    const fireFinale = (): void => {
      if (finaleFired) return;
      finaleFired = true;
      crowd.classList.add("rise");
      lights.classList.add("on");
      finale.classList.add("show");
      const target = 14.8;
      const startT = performance.now();
      const dur = 900;
      const tick = (t: number): void => {
        const k = Math.min(1, (t - startT) / dur);
        const e = 1 - Math.pow(1 - k, 3);
        finaleVal.textContent = (target * e).toFixed(1);
        if (k < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    };

    const resetFinale = (): void => {
      finaleFired = false;
      crowd.classList.remove("rise");
      lights.classList.remove("on");
      finale.classList.remove("show");
    };

    const update = (): void => {
      const rect = stage.getBoundingClientRect();
      const stageH = rect.height - window.innerHeight;
      const rawProgress = clamp(-rect.top / stageH, 0, 1);
      const progress = physicsWarp(rawProgress);

      path.setAttribute("stroke-dashoffset", String((1 - rawProgress) * pathLen));

      const pt = path.getPointAtLength(progress * totalLen);

      const dx = pt.x - prevPt.x;
      const dy = pt.y - prevPt.y;
      const speed = Math.sqrt(dx * dx + dy * dy);
      const blur = clamp(speed * 0.12, 0, 3.5);
      blurStd.setAttribute("stdDeviation", blur.toFixed(2));

      const rot = (rawProgress * 1440) % 360;
      ball.setAttribute("transform", `translate(${pt.x},${pt.y}) rotate(${rot})`);

      if (rawProgress > 0.01 && Math.abs(rawProgress - lastProgress) > 0.006) {
        updateTrail(pt);
        lastProgress = rawProgress;
      }

      if (speed > 2) {
        const angle = Math.atan2(dy, dx);
        const streakLenPx = clamp(speed * 3, 10, 60);
        const tailX = pt.x - Math.cos(angle) * streakLenPx;
        const tailY = pt.y - Math.sin(angle) * streakLenPx;
        streakLine.setAttribute("x1", String(tailX));
        streakLine.setAttribute("y1", String(tailY));
        streakLine.setAttribute("x2", String(pt.x));
        streakLine.setAttribute("y2", String(pt.y));
        streakG.setAttribute("opacity", String(Math.min(1, speed / 15)));
      } else {
        streakG.setAttribute("opacity", "0");
      }

      const altitude = clamp((760 - pt.y) / 700, 0, 1);
      const shadowScale = 1 - altitude * 0.7;
      const shadowOp = (1 - altitude) * 0.8;
      shadow.setAttribute("cx", String(pt.x));
      shadow.setAttribute("rx", String(26 * shadowScale));
      shadow.setAttribute("ry", String(7 * shadowScale));
      shadow.setAttribute("opacity", rawProgress > 0.02 ? String(shadowOp) : "0");

      if (rawProgress > 0.015 && !swingFired) fireSwing();
      if (rawProgress < 0.01 && swingFired) {
        swingFired = false;
        batter.classList.remove("show", "swung");
      }

      for (let i = 0; i < DAMAGE_DATA.length; i++) {
        const d = DAMAGE_DATA[i];
        if (!damageFired[i] && rawProgress >= d.at) {
          spawnDamage(pt.x, pt.y, d.k, d.v);
          damageFired[i] = true;
        }
        if (damageFired[i] && rawProgress < d.at - 0.05) damageFired[i] = false;
      }

      if (rawProgress > 0.88 && !finaleFired) fireFinale();
      if (rawProgress < 0.82 && finaleFired) resetFinale();

      prevPt = pt;
    };

    const onScroll = (): void => {
      window.requestAnimationFrame(update);
    };

    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    window.requestAnimationFrame(update);

    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, []);

  return (
    <section className="arc" id="arc">
      <div className="arc-head">
        <span className="section-num">/ 02</span>
        <h2 className="section-title">
          FROM CONTACT<br />
          TO <span className="accent">COLD PROBABILITY</span>.
        </h2>
        <p className="section-kicker">
          Scroll. Watch the ball leave the bat — and every variable that turns it
          into a number.
        </p>
      </div>

      <div className="arc-stage" ref={stageRef}>
        <div className="arc-pin">
          <div className="contact-flash" ref={contactFlashRef} />

          <div className="crowd-silhouette" ref={crowdRef} aria-hidden="true">
            <svg viewBox="0 0 1600 260" preserveAspectRatio="none">
              <path
                d="M0,260 L0,200 Q20,180 40,200 Q60,160 80,200 Q100,170 120,200 Q140,150 160,200 Q180,180 200,200 Q220,150 240,200 Q260,170 280,200 Q300,160 320,200 Q340,180 360,200 Q380,150 400,200 Q420,170 440,200 Q460,160 480,200 Q500,180 520,200 Q540,150 560,200 Q580,170 600,200 Q620,160 640,200 Q660,180 680,200 Q700,150 720,200 Q740,170 760,200 Q780,160 800,200 Q820,180 840,200 Q860,150 880,200 Q900,170 920,200 Q940,160 960,200 Q980,180 1000,200 Q1020,150 1040,200 Q1060,170 1080,200 Q1100,160 1120,200 Q1140,180 1160,200 Q1180,150 1200,200 Q1220,170 1240,200 Q1260,160 1280,200 Q1300,180 1320,200 Q1340,150 1360,200 Q1380,170 1400,200 Q1420,160 1440,200 Q1460,180 1480,200 Q1500,150 1520,200 Q1540,170 1560,200 Q1580,180 1600,200 L1600,260 Z"
                fill="rgba(0,0,0,.9)"
              />
            </svg>
          </div>

          <div className="stadium-lights" ref={lightsRef} aria-hidden="true">
            <div className="sl sl-1" />
            <div className="sl sl-2" />
            <div className="sl sl-3" />
            <div className="sl sl-4" />
          </div>

          <div className="batter" ref={batterRef} aria-hidden="true">
            <svg viewBox="0 0 120 200" preserveAspectRatio="xMidYMax meet">
              <g id="bat-swing">
                <rect x="58" y="-30" width="4" height="70" rx="2" fill="#0a0a0a" />
                <rect x="56" y="-50" width="8" height="26" rx="4" fill="#3a2a1a" />
              </g>
              <g fill="#0a0a0a">
                <circle cx="60" cy="38" r="14" />
                <path d="M44 50 L76 50 L82 130 L70 180 L50 180 L38 130 Z" />
                <rect x="48" y="175" width="10" height="22" rx="2" />
                <rect x="62" y="175" width="10" height="22" rx="2" />
                <rect x="46" y="24" width="28" height="4" fill="var(--accent)" />
              </g>
            </svg>
          </div>

          <svg
            className="arc-svg"
            viewBox="0 0 1600 900"
            preserveAspectRatio="none"
            aria-hidden="true"
          >
            <defs>
              <linearGradient id="arcGrad" x1="0" y1="0" x2="1" y2="0">
                <stop offset="0%" stopColor="var(--accent)" stopOpacity="0" />
                <stop offset="40%" stopColor="var(--accent)" stopOpacity=".6" />
                <stop offset="100%" stopColor="var(--accent)" stopOpacity=".9" />
              </linearGradient>
              <filter id="arcGlow">
                <feGaussianBlur stdDeviation="6" />
              </filter>
              <filter id="ballBlur">
                <feGaussianBlur stdDeviation="0" ref={blurStdRef} />
              </filter>
              <radialGradient id="ballGrad" cx="35%" cy="35%">
                <stop offset="0%" stopColor="#ffffff" />
                <stop offset="45%" stopColor="#f4e8d6" />
                <stop offset="85%" stopColor="#cbb89c" />
                <stop offset="100%" stopColor="#8a7656" />
              </radialGradient>
              <radialGradient id="shadowGrad" cx="50%" cy="50%">
                <stop offset="0%" stopColor="rgba(0,0,0,.55)" />
                <stop offset="70%" stopColor="rgba(0,0,0,.2)" />
                <stop offset="100%" stopColor="rgba(0,0,0,0)" />
              </radialGradient>
            </defs>

            <line x1="0" y1="760" x2="1600" y2="760" stroke="rgba(255,255,255,.08)" strokeDasharray="6 10" />
            <line x1="1420" y1="760" x2="1420" y2="640" stroke="rgba(255,255,255,.2)" strokeWidth="2" strokeDasharray="3 6" />
            <text x="1430" y="655" fill="rgba(255,255,255,.35)" fontSize="14" letterSpacing="2">WALL</text>

            <ellipse
              ref={shadowRef}
              cx="120" cy="762" rx="24" ry="6"
              fill="url(#shadowGrad)" opacity="0"
            />

            <path
              ref={pathRef}
              d="M 160 720 Q 800 -180 1500 560"
              fill="none"
              stroke="url(#arcGrad)"
              strokeWidth="2"
              filter="url(#arcGlow)"
              pathLength={1000}
              strokeDasharray="1000"
              strokeDashoffset="1000"
            />

            <g ref={trailRef} />
            <g ref={damageRef} />

            <g ref={ballRef} filter="url(#ballBlur)">
              <circle className="ball-body" r="22" fill="url(#ballGrad)" />
              <path d="M -18 -4 Q 0 -18 18 -4" stroke="#c8302a" strokeWidth="2" fill="none" strokeLinecap="round" />
              <path d="M -18 4 Q 0 18 18 4" stroke="#c8302a" strokeWidth="2" fill="none" strokeLinecap="round" />
              <g stroke="#c8302a" strokeWidth="1.1" strokeLinecap="round">
                <line x1="-14" y1="-7" x2="-13" y2="-3" />
                <line x1="-8" y1="-11" x2="-7" y2="-7" />
                <line x1="0" y1="-12" x2="0" y2="-8" />
                <line x1="8" y1="-11" x2="7" y2="-7" />
                <line x1="14" y1="-7" x2="13" y2="-3" />
                <line x1="-14" y1="7" x2="-13" y2="3" />
                <line x1="-8" y1="11" x2="-7" y2="7" />
                <line x1="0" y1="12" x2="0" y2="8" />
                <line x1="8" y1="11" x2="7" y2="7" />
                <line x1="14" y1="7" x2="13" y2="3" />
              </g>
              <ellipse cx="-7" cy="-7" rx="5" ry="3" fill="rgba(255,255,255,.5)" />
            </g>

            <g ref={streakGRef} opacity="0">
              <line
                ref={streakLineRef}
                x1="0" y1="0" x2="0" y2="0"
                stroke="rgba(244,232,214,.5)" strokeWidth="4" strokeLinecap="round"
                filter="url(#arcGlow)"
              />
            </g>
          </svg>

          <div className="stadium" aria-hidden="true">
            <svg viewBox="0 0 1600 300" preserveAspectRatio="none">
              <path
                d="M0,300 L0,180 L80,180 L100,150 L200,150 L220,120 L360,120 L380,100 L520,100 L540,80 L780,80 L800,60 L820,80 L1060,80 L1080,100 L1220,100 L1240,120 L1380,120 L1400,150 L1500,150 L1520,180 L1600,180 L1600,300 Z"
                fill="rgba(255,255,255,.04)"
              />
            </svg>
          </div>

          <div className="finale-number" ref={finaleRef} aria-hidden="true">
            <div className="fn-label">FINAL · P(HR)</div>
            <div className="fn-value">
              <span ref={finaleValRef}>0.0</span>
              <span className="fn-pct">%</span>
            </div>
            <div className="fn-sub">RANK #1 · 412 HITTERS · TONIGHT</div>
          </div>
        </div>
      </div>
    </section>
  );
}
