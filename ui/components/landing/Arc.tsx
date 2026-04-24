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
// Minimum SVG-unit distance between ghost trail positions. Distance-gated
// rather than scroll-delta-gated so the buffer always fills — solves the
// "intermittent 1-3 circles" issue Claude Design's verifier flagged.
const TRAIL_STRIDE = 44;
// Baseball radius in SVG units. viewBox is 1600×900, path spans x:160→1500,
// so 52 reads as ~40–50 CSS px on a typical laptop viewport. Doubled from
// the original 22 because the stitching was invisible at that scale.
const BALL_R = 52;
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

    const renderTrail = (): void => {
      trail.innerHTML = trailBuf
        .slice(1)
        .map((t, i) => {
          const age = (i + 1) / TRAIL_LEN;
          const r = BALL_R * 0.9 * (1 - age * 0.65);
          const op = (1 - age) * 0.55;
          return `<circle class="trail-dot" cx="${t.x}" cy="${t.y}" r="${r}" opacity="${op}"/>`;
        })
        .join("");
    };

    const pushTrailIfStrided = (pt: TrailPt): void => {
      const latest = trailBuf[0];
      const dist = latest
        ? Math.hypot(pt.x - latest.x, pt.y - latest.y)
        : Infinity;
      if (dist < TRAIL_STRIDE) return;
      trailBuf.unshift({ x: pt.x, y: pt.y });
      if (trailBuf.length > TRAIL_LEN) trailBuf.length = TRAIL_LEN;
      renderTrail();
    };

    const resetTrail = (): void => {
      trailBuf.length = 0;
      trail.innerHTML = "";
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

      // Backward-scroll reset: if user scrubs back to near the start, wipe
      // the trail so ghost balls don't linger at stale forward positions.
      if (rawProgress < lastProgress - 0.05) {
        resetTrail();
      }
      if (rawProgress > 0.01) {
        pushTrailIfStrided(pt);
      } else if (trailBuf.length > 0) {
        resetTrail();
      }
      lastProgress = rawProgress;

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
      shadow.setAttribute("rx", String(BALL_R * 1.15 * shadowScale));
      shadow.setAttribute("ry", String(BALL_R * 0.3 * shadowScale));
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
            <svg viewBox="0 0 120 220" preserveAspectRatio="xMidYMax meet">
              {/* Bat — barrel + taper + grip + knob. Swings via #bat-swing transform. */}
              <g id="bat-swing">
                <rect x="57" y="-40" width="7" height="80" rx="3" fill="#1a0f08" stroke="#0a0a0a" strokeWidth="0.8" />
                <rect x="56" y="-58" width="10" height="18" rx="2" fill="#3a2a1a" />
                <rect x="54" y="-62" width="14" height="6" rx="2" fill="#0a0a0a" />
                {/* grip wrap */}
                <line x1="56" y1="-52" x2="66" y2="-52" stroke="#0a0a0a" strokeWidth="0.8" />
                <line x1="56" y1="-46" x2="66" y2="-46" stroke="#0a0a0a" strokeWidth="0.8" />
              </g>
              {/* Body silhouette */}
              <g fill="#0a0a0a">
                {/* Legs — wider batting stance */}
                <rect x="40" y="160" width="14" height="40" rx="4" />
                <rect x="66" y="160" width="14" height="40" rx="4" />
                {/* Cleats */}
                <rect x="34" y="196" width="24" height="6" rx="2" />
                <rect x="62" y="196" width="24" height="6" rx="2" />
                {/* Torso — tapered V with hips */}
                <path d="M 30 62 L 90 62 L 86 110 L 82 155 L 70 160 L 50 160 L 38 155 L 34 110 Z" />
                {/* Shoulders + belt accent */}
                <rect x="28" y="58" width="64" height="10" rx="5" />
                <rect x="46" y="118" width="28" height="3" fill="rgba(255,255,255,.08)" />
                {/* Helmet / head */}
                <circle cx="60" cy="42" r="20" />
                {/* Face shadow strip */}
                <rect x="42" y="44" width="36" height="8" rx="2" fill="rgba(255,255,255,.04)" />
                {/* Clay helmet stripe */}
                <rect x="40" y="26" width="40" height="6" rx="2" fill="var(--accent)" />
                {/* Ear flap */}
                <path d="M 40 42 Q 36 50 40 58 L 46 58 L 46 42 Z" />
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

            <line x1="0" y1="760" x2="1600" y2="760" stroke="rgba(255,255,255,.16)" strokeDasharray="8 14" strokeWidth="1.5" />
            <line x1="1420" y1="760" x2="1420" y2="620" stroke="rgba(255,255,255,.45)" strokeWidth="3" strokeDasharray="4 8" />
            <text x="1432" y="632" fill="rgba(255,255,255,.7)" fontSize="22" letterSpacing="3" fontWeight="700">WALL</text>

            <ellipse
              ref={shadowRef}
              cx="120" cy="762" rx="60" ry="15"
              fill="url(#shadowGrad)" opacity="0"
            />

            <path
              ref={pathRef}
              d="M 160 720 Q 800 -180 1500 560"
              fill="none"
              stroke="url(#arcGrad)"
              strokeWidth="3.5"
              filter="url(#arcGlow)"
              pathLength={1000}
              strokeDasharray="1000"
              strokeDashoffset="1000"
            />

            <g ref={trailRef} />
            <g ref={damageRef} />

            <g ref={ballRef} filter="url(#ballBlur)">
              {/* Soft halo behind the ball so it reads against the dark arc */}
              <circle r={BALL_R * 1.35} fill="rgba(244,232,214,.08)" />
              <circle r={BALL_R * 1.1} fill="rgba(244,232,214,.12)" />
              {/* Ball body */}
              <circle className="ball-body" r={BALL_R} fill="url(#ballGrad)" stroke="rgba(138,118,86,.6)" strokeWidth="1" />
              {/* Two curving seams — r≈52 so the visible stitch curve sits at ±42 */}
              <path
                d={`M ${-BALL_R * 0.82} ${-BALL_R * 0.18} Q 0 ${-BALL_R * 0.82} ${BALL_R * 0.82} ${-BALL_R * 0.18}`}
                stroke="#c8302a" strokeWidth="4" fill="none" strokeLinecap="round"
              />
              <path
                d={`M ${-BALL_R * 0.82} ${BALL_R * 0.18} Q 0 ${BALL_R * 0.82} ${BALL_R * 0.82} ${BALL_R * 0.18}`}
                stroke="#c8302a" strokeWidth="4" fill="none" strokeLinecap="round"
              />
              {/* Stitch ticks: five along each seam, perpendicular-ish */}
              <g stroke="#c8302a" strokeWidth="2.5" strokeLinecap="round">
                <line x1={-BALL_R * 0.64} y1={-BALL_R * 0.32} x2={-BALL_R * 0.58} y2={-BALL_R * 0.14} />
                <line x1={-BALL_R * 0.36} y1={-BALL_R * 0.5}  x2={-BALL_R * 0.3}  y2={-BALL_R * 0.32} />
                <line x1="0"              y1={-BALL_R * 0.55} x2="0"              y2={-BALL_R * 0.36} />
                <line x1={BALL_R * 0.36}  y1={-BALL_R * 0.5}  x2={BALL_R * 0.3}   y2={-BALL_R * 0.32} />
                <line x1={BALL_R * 0.64}  y1={-BALL_R * 0.32} x2={BALL_R * 0.58}  y2={-BALL_R * 0.14} />
                <line x1={-BALL_R * 0.64} y1={BALL_R * 0.32}  x2={-BALL_R * 0.58} y2={BALL_R * 0.14}  />
                <line x1={-BALL_R * 0.36} y1={BALL_R * 0.5}   x2={-BALL_R * 0.3}  y2={BALL_R * 0.32}  />
                <line x1="0"              y1={BALL_R * 0.55}  x2="0"              y2={BALL_R * 0.36}  />
                <line x1={BALL_R * 0.36}  y1={BALL_R * 0.5}   x2={BALL_R * 0.3}   y2={BALL_R * 0.32}  />
                <line x1={BALL_R * 0.64}  y1={BALL_R * 0.32}  x2={BALL_R * 0.58}  y2={BALL_R * 0.14}  />
              </g>
              {/* Specular highlight — sphere fakery */}
              <ellipse
                cx={-BALL_R * 0.32} cy={-BALL_R * 0.32}
                rx={BALL_R * 0.26} ry={BALL_R * 0.15}
                fill="rgba(255,255,255,.55)"
              />
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
