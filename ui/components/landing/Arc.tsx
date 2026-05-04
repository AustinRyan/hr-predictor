"use client";

import { useEffect, useRef, useState } from "react";

type DamageEvent = { at: number; k: string; v: string };
const DAMAGE_DATA: readonly DamageEvent[] = [
  { at: 0.1, k: "EXIT VELOCITY", v: "108.3 MPH" },
  { at: 0.3, k: "LAUNCH ANGLE", v: "28.4°" },
  { at: 0.55, k: "WIND VECTOR", v: "↗ 11 MPH" },
  { at: 0.8, k: "CARRY", v: "+1.4 MPH" },
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

function MobileArcPanel() {
  return (
    <div className="arc-mobile-panel" aria-label="Home run arc summary">
      <div className="arc-mobile-visual" aria-hidden="true">
        <svg viewBox="0 0 360 240" preserveAspectRatio="xMidYMid meet">
          <defs>
            <linearGradient id="mobileArcGrad" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="var(--accent)" stopOpacity=".2" />
              <stop offset="55%" stopColor="var(--accent)" stopOpacity=".85" />
              <stop offset="100%" stopColor="var(--accent-2)" stopOpacity=".95" />
            </linearGradient>
            <radialGradient id="mobileBallGrad" cx="35%" cy="35%">
              <stop offset="0%" stopColor="#fff" />
              <stop offset="50%" stopColor="#f4e8d6" />
              <stop offset="100%" stopColor="#b79c77" />
            </radialGradient>
          </defs>
          <path d="M 20 205 L 340 205" stroke="rgba(255,255,255,.14)" strokeDasharray="5 8" />
          <path
            d="M 32 194 Q 172 -42 326 100"
            fill="none"
            stroke="url(#mobileArcGrad)"
            strokeWidth="3"
            strokeLinecap="round"
          />
          <g opacity=".36">
            <circle cx="108" cy="110" r="13" fill="#f4e8d6" />
            <circle cx="172" cy="56" r="10" fill="#f4e8d6" />
            <circle cx="236" cy="62" r="7" fill="#f4e8d6" />
          </g>
          <g transform="translate(306 112) rotate(18)">
            <circle r="20" fill="url(#mobileBallGrad)" stroke="rgba(138,118,86,.7)" />
            <path d="M -14 -5 Q 0 -17 14 -5" stroke="#c8302a" strokeWidth="2" fill="none" strokeLinecap="round" />
            <path d="M -14 5 Q 0 17 14 5" stroke="#c8302a" strokeWidth="2" fill="none" strokeLinecap="round" />
          </g>
        </svg>
      </div>

      <div className="arc-mobile-copy">
        <div className="arc-mobile-k">Flight read</div>
        <div className="arc-mobile-v">14.8<span>%</span></div>
        <div className="arc-mobile-sub">Final P(HR) · variable summary</div>
      </div>

      <div className="arc-mobile-factors">
        {DAMAGE_DATA.map((item) => (
          <div className="arc-mobile-factor" key={item.k}>
            <span>{item.k}</span>
            <b>{item.v}</b>
          </div>
        ))}
      </div>
    </div>
  );
}

export function Arc() {
  const [compactArc, setCompactArc] = useState(false);
  const stageRef = useRef<HTMLDivElement | null>(null);
  const pathRef = useRef<SVGPathElement | null>(null);
  const ballRef = useRef<SVGGElement | null>(null);
  const shadowRef = useRef<SVGEllipseElement | null>(null);
  const trailRef = useRef<SVGGElement | null>(null);
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
    const query = window.matchMedia("(max-width: 760px), (pointer: coarse)");
    const sync = (): void => setCompactArc(query.matches);
    sync();
    query.addEventListener("change", sync);
    return () => query.removeEventListener("change", sync);
  }, []);

  useEffect(() => {
    if (compactArc) return;
    const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (prefersReduced) return;

    const stage = stageRef.current;
    const path = pathRef.current;
    const ball = ballRef.current;
    const shadow = shadowRef.current;
    const trail = trailRef.current;
    const blurStd = blurStdRef.current;
    const streakG = streakGRef.current;
    const streakLine = streakLineRef.current;
    const batter = batterRef.current;
    const contactFlash = contactFlashRef.current;
    const crowd = crowdRef.current;
    const lights = lightsRef.current;
    const finale = finaleRef.current;
    const finaleVal = finaleValRef.current;

    if (!stage || !path || !ball || !shadow || !trail || !blurStd ||
        !streakG || !streakLine || !batter || !contactFlash || !crowd || !lights ||
        !finale || !finaleVal) {
      return;
    }

    const pin = stage.querySelector<HTMLDivElement>(":scope > .arc-pin");
    if (!pin) return;

    const totalLen = path.getTotalLength();
    const pathLen = 1000;

    type TrailPt = { x: number; y: number };
    const trailBuf: TrailPt[] = [];
    // Per-threshold last-fire timestamp (ms). Used for a cooldown so
    // damages re-fire on reverse-scroll crossings without spamming.
    const damageLastFire = new Array(DAMAGE_DATA.length).fill(0);
    const DAMAGE_COOLDOWN_MS = 1200;
    const DAMAGE_WINDOW = 0.025;
    let swingFired = false;
    let finaleFired = false;
    let prevPt = path.getPointAtLength(0);
    let lastProgress = 0;
    let activeDamage: HTMLElement | null = null;

    const spawnDamage = (x: number, y: number, k: string, v: string): void => {
      // Damage numbers render as HTML <div>s with `position: fixed` at
      // the document body. Why not SVG text or absolute-inside-arc-pin?
      // After extensive Playwright inspection, both paths hit Chromium
      // compositor bugs: elements added mid-scroll inside a `sticky`
      // container don't get rasterized even when computed styles report
      // full opacity + valid bboxes. Rendering on the body with `fixed`
      // positioning sidesteps the whole sticky-context ordeal. When the
      // arc-pin is on screen, fixed positioning already equals what we
      // want (pinned to the viewport), and when the user scrolls past
      // the arc the damage gets auto-removed by the 2700ms timeout.
      if (!pin) return;
      const pinRect = pin.getBoundingClientRect();
      // Only spawn if the pin is actually in the viewport.
      if (pinRect.bottom < 0 || pinRect.top > window.innerHeight) return;
      const cssX = pinRect.left + (x / 1600) * pinRect.width;
      const cssY = pinRect.top + (y / 900) * pinRect.height;

      // Only one damage visible at a time — retire any predecessor before
      // its tail fade completes so WIND and PARK (close in time) don't
      // stack on top of each other.
      if (activeDamage) {
        const prev = activeDamage;
        prev.classList.add("arc-damage-out");
        window.setTimeout(() => {
          if (prev.parentNode) prev.parentNode.removeChild(prev);
        }, 500);
      }

      const el = document.createElement("div");
      el.className = "arc-damage";
      el.style.left = `${cssX}px`;
      el.style.top = `${cssY}px`;
      el.innerHTML =
        `<div class="arc-damage-k">${k}</div>` +
        `<div class="arc-damage-v">${v}</div>`;
      document.body.appendChild(el);
      activeDamage = el;

      window.setTimeout(() => {
        if (el === activeDamage) el.classList.add("arc-damage-out");
      }, 2000);
      window.setTimeout(() => {
        if (el.parentNode) el.parentNode.removeChild(el);
        if (el === activeDamage) activeDamage = null;
      }, 2700);
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
      const prevRaw = lastProgress;
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

      // Bidirectional damage firing: a threshold fires whenever progress
      // crosses it in EITHER direction, with a per-threshold cooldown so
      // scrubbing past the same line doesn't spam the viewport. This
      // makes reverse-scroll replay EV/LA/WIND/PARK/CARRY as the user
      // scrolls back up through the arc.
      const now = performance.now();
      const dp = Math.abs(rawProgress - prevRaw);
      for (let i = 0; i < DAMAGE_DATA.length; i++) {
        const d = DAMAGE_DATA[i];
        const crossed =
          (prevRaw < d.at && rawProgress >= d.at) ||
          (prevRaw > d.at && rawProgress <= d.at) ||
          // Also fire when we "teleport" (big scroll jump) into the
          // threshold's neighborhood for the first time.
          (dp > 0.15 && Math.abs(rawProgress - d.at) < DAMAGE_WINDOW);
        if (crossed && now - damageLastFire[i] > DAMAGE_COOLDOWN_MS) {
          spawnDamage(pt.x, pt.y, d.k, d.v);
          damageLastFire[i] = now;
        }
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
  }, [compactArc]);

  return (
    <section className="arc" id="arc">
      <div className="arc-head">
        <span className="section-num">/ 02</span>
        <h2 className="section-title">
          FROM CONTACT<br />
          TO <span className="accent">COLD PROBABILITY</span>.
        </h2>
        <p className="section-kicker">
          Watch the ball leave the bat — and every variable that turns it into a
          number.
        </p>
      </div>

      <MobileArcPanel />

      {!compactArc && <div className="arc-stage" ref={stageRef}>
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
              <defs>
                {/* Wood-grain gradient for the bat: lighter at barrel end,
                    darker at handle — ash/maple color range. */}
                <linearGradient id="batWood" x1="0" y1="-65" x2="0" y2="30" gradientUnits="userSpaceOnUse">
                  <stop offset="0%" stopColor="#b6823d" />
                  <stop offset="35%" stopColor="#8f5a24" />
                  <stop offset="70%" stopColor="#5a3612" />
                  <stop offset="100%" stopColor="#2a1808" />
                </linearGradient>
                <linearGradient id="batShine" x1="0" y1="0" x2="1" y2="0">
                  <stop offset="0%" stopColor="rgba(255,255,255,0)" />
                  <stop offset="50%" stopColor="rgba(255,240,210,.25)" />
                  <stop offset="100%" stopColor="rgba(255,255,255,0)" />
                </linearGradient>
                <radialGradient id="helmetDome" cx="40%" cy="25%">
                  <stop offset="0%" stopColor="rgba(255,255,255,.14)" />
                  <stop offset="70%" stopColor="rgba(255,255,255,0)" />
                </radialGradient>
              </defs>

              {/* BAT + HANDS — swing group, rotates around (60, 44) per CSS. */}
              <g id="bat-swing">
                {/* Barrel (thickest end, farthest from hands) */}
                <path d="M 60 -68 Q 55 -68 55 -62 L 56 -10 Q 56 -6 60 -6 Q 64 -6 64 -10 L 65 -62 Q 65 -68 60 -68 Z"
                      fill="url(#batWood)" stroke="#0a0604" strokeWidth="0.4" />
                {/* Shine highlight along barrel */}
                <rect x="57" y="-60" width="6" height="52" fill="url(#batShine)" opacity="0.4" />
                {/* Taper into handle */}
                <path d="M 56 -10 L 64 -10 L 63 8 L 57 8 Z" fill="url(#batWood)" />
                {/* Grip tape */}
                <rect x="58" y="8" width="4" height="20" fill="#1a0f06" />
                {/* Grip wrap lines */}
                <line x1="58" y1="12" x2="62" y2="12" stroke="#3a2a18" strokeWidth="0.5" />
                <line x1="58" y1="17" x2="62" y2="17" stroke="#3a2a18" strokeWidth="0.5" />
                <line x1="58" y1="22" x2="62" y2="22" stroke="#3a2a18" strokeWidth="0.5" />
                {/* Knob */}
                <ellipse cx="60" cy="29" rx="4" ry="2" fill="#0a0604" />

                {/* Hands / batting gloves — sit ON the grip, rotate with bat. */}
                <path d="M 50 38 Q 46 48 52 54 Q 60 58 68 54 Q 74 48 70 38 Q 64 34 60 34 Q 56 34 50 38 Z"
                      fill="#181008" stroke="#0a0604" strokeWidth="0.5" />
                <path d="M 52 46 L 68 46" stroke="rgba(var(--accent-rgb),.65)" strokeWidth="1.2" />
                <path d="M 53 50 L 67 50" stroke="rgba(0,0,0,.4)" strokeWidth="0.6" />
              </g>

              {/* BODY — stationary during swing. Silhouette all black. */}
              <g fill="#1b1f2d">
                {/* BACK leg (right leg of RHB, at low x) — coiled */}
                <path d="M 30 128 Q 22 138 24 168 L 28 208 L 48 208 L 46 168 Q 44 142 48 126 Z" />
                {/* FRONT leg (left leg of RHB, at high x) — planted */}
                <path d="M 72 130 Q 84 138 86 170 L 88 208 L 74 208 L 72 170 Q 70 144 74 128 Z" />
                {/* Cleats */}
                <path d="M 20 204 L 50 204 L 48 214 L 22 214 Z" />
                <path d="M 70 204 L 92 204 L 90 214 L 72 214 Z" />
                {/* Hips */}
                <path d="M 36 118 L 84 118 L 80 138 L 40 138 Z" />
                {/* Torso — wide shoulders tapering to waist */}
                <path d="M 28 62 Q 60 55 92 62 L 88 100 L 82 118 L 38 118 L 32 100 Z" />
                {/* Back (right) shoulder — raised, rounded */}
                <ellipse cx="35" cy="64" rx="10" ry="8" />
                {/* Front (left) shoulder */}
                <ellipse cx="85" cy="64" rx="10" ry="8" />
                {/* Upper arms reaching from shoulders toward bat pivot (60,44) */}
                {/* Back arm (RHB's right, drawn top-and-back from right shoulder) */}
                <path d="M 30 56 Q 36 44 52 40 L 58 48 Q 46 54 38 62 Z" />
                {/* Front (lead) arm — comes across body to grip */}
                <path d="M 86 58 Q 78 48 66 42 L 62 50 Q 74 56 82 64 Z" />
                {/* Neck */}
                <rect x="54" y="46" width="12" height="10" />
                {/* Head / helmet — rounded dome with slight egg shape */}
                <path d="M 60 8 Q 42 8 38 24 Q 36 38 42 48 Q 50 54 60 52 Q 70 54 78 48 Q 84 38 82 24 Q 78 8 60 8 Z" />
                {/* Ear flap (on pitcher side = front = right in SVG) */}
                <path d="M 80 30 Q 84 40 82 48 L 74 48 L 74 30 Z" />
                {/* Jaw shadow */}
                <path d="M 58 52 Q 54 56 52 52" fill="rgba(255,255,255,.04)" />
              </g>

              {/* Helmet dome highlight — subtle sheen */}
              <ellipse cx="52" cy="22" rx="20" ry="16" fill="url(#helmetDome)" />
              {/* Clay accent stripe across helmet crown */}
              <path d="M 44 16 Q 60 10 76 16 L 76 22 Q 60 14 44 22 Z" fill="var(--accent)" />

              {/* Belt line */}
              <rect x="40" y="118" width="40" height="1.5" fill="rgba(255,255,255,.12)" />
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
      </div>}
    </section>
  );
}
