import type { CSSProperties } from "react";
import {
  AbsoluteFill,
  Audio,
  Easing,
  Sequence,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

export type HomerunPromoProps = {
  slateDate: string;
  modelVersion: string;
};

const colors = {
  bg: "#050507",
  panel: "#0d111a",
  panel2: "#121826",
  ink: "#f7eee5",
  dim: "#8b929d",
  mute: "#555d6c",
  line: "rgba(247,238,229,0.14)",
  accent: "#ff5a1f",
  accentDeep: "#a92d0c",
  green: "#75f2b8",
};

const fontDisplay =
  '"Avenir Next Condensed", "Barlow Condensed", "Arial Narrow", Impact, sans-serif';
const fontMono = '"JetBrains Mono", "SFMono-Regular", Menlo, Consolas, monospace';
const fontBody = '"Archivo", "Avenir Next", Arial, sans-serif';

const picks = [
  {
    rank: "01",
    name: "MAX MUNCY",
    vs: "vs JANSON JUNK",
    park: "DODGER STADIUM",
    prob: "15.4%",
    factors: ["BRL 10%", "PARK +23", "MODEL +0.16"],
  },
  {
    rank: "02",
    name: "BYRON BUXTON",
    vs: "vs LOGAN GILBERT",
    park: "TARGET FIELD",
    prob: "15.4%",
    factors: ["BRL 10%", "PARK -3", "MODEL +0.15"],
  },
  {
    rank: "03",
    name: "SHOHEI OHTANI",
    vs: "vs JANSON JUNK",
    park: "DODGER STADIUM",
    prob: "15.4%",
    factors: ["BRL 12%", "PARK +23", "MODEL +0.18"],
  },
];

const clamp = {
  extrapolateLeft: "clamp" as const,
  extrapolateRight: "clamp" as const,
};

const easeOut = Easing.bezier(0.16, 1, 0.3, 1);
const easeInOut = Easing.bezier(0.45, 0, 0.55, 1);

function sec(value: number, fps: number): number {
  return Math.round(value * fps);
}

function timed(
  frame: number,
  fps: number,
  start: number,
  duration: number,
  easing = easeOut,
): number {
  return interpolate(frame, [sec(start, fps), sec(start + duration, fps)], [0, 1], {
    ...clamp,
    easing,
  });
}

function fadeOut(frame: number, fps: number, start: number, duration: number): number {
  return interpolate(frame, [sec(start, fps), sec(start + duration, fps)], [1, 0], {
    ...clamp,
    easing: Easing.in(Easing.cubic),
  });
}

function lineStyle(index: number): CSSProperties {
  return {
    position: "absolute",
    left: 0,
    right: 0,
    top: `${index * 7.5}%`,
    height: 1,
    background: "rgba(247,238,229,0.045)",
  };
}

const ScreenTexture = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pulse = interpolate(
    Math.sin(frame / fps),
    [-1, 1],
    [0.18, 0.32],
  );

  return (
    <AbsoluteFill>
      <div
        style={{
          position: "absolute",
          inset: 0,
          background:
            "radial-gradient(circle at 50% 22%, rgba(255,90,31,0.18), transparent 30%), radial-gradient(circle at 10% 80%, rgba(255,90,31,0.10), transparent 32%), #050507",
        }}
      />
      <div
        style={{
          position: "absolute",
          inset: -220,
          opacity: 0.16 + pulse,
          transform: `rotate(${frame * 0.015}deg)`,
          background:
            "conic-gradient(from 0deg, transparent, rgba(255,90,31,0.12), transparent, rgba(247,238,229,0.05), transparent)",
        }}
      />
      {Array.from({ length: 15 }, (_, index) => (
        <div key={index} style={lineStyle(index)} />
      ))}
      <div
        style={{
          position: "absolute",
          inset: 0,
          opacity: 0.11,
          background:
            "repeating-linear-gradient(0deg, rgba(255,255,255,.08) 0px, rgba(255,255,255,.08) 1px, transparent 1px, transparent 6px)",
        }}
      />
      <div
        style={{
          position: "absolute",
          inset: 0,
          boxShadow: "inset 0 0 240px rgba(0,0,0,.95)",
        }}
      />
    </AbsoluteFill>
  );
};

const Header = ({ slateDate, modelVersion }: HomerunPromoProps) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const inProgress = timed(frame, fps, 0.1, 0.8);

  return (
    <div
      style={{
        position: "absolute",
        top: 58,
        left: 58,
        right: 58,
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        opacity: inProgress,
        transform: `translateY(${interpolate(inProgress, [0, 1], [-18, 0])}px)`,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <div
          style={{
            width: 14,
            height: 14,
            background: colors.accent,
            transform: "rotate(45deg)",
          }}
        />
        <div
          style={{
            fontFamily: fontDisplay,
            color: colors.ink,
            fontSize: 40,
            fontWeight: 900,
            letterSpacing: 3,
          }}
        >
          HOMERUN
        </div>
      </div>
      <div
        style={{
          fontFamily: fontMono,
          color: colors.dim,
          fontSize: 19,
          letterSpacing: 4,
          textAlign: "right",
        }}
      >
        {slateDate}
        <br />
        {modelVersion}
      </div>
    </div>
  );
};

const BallArc = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const flight = timed(frame, fps, 1.4, 10.8, easeInOut);
  const exit = timed(frame, fps, 13.1, 0.7);
  const x = interpolate(flight, [0, 1], [-70, 1130]);
  const y = 1220 - Math.sin(flight * Math.PI) * 720 - flight * 220;
  const scale = interpolate(flight, [0, 0.48, 1], [0.8, 1.35, 0.72]);
  const opacity = Math.min(timed(frame, fps, 0.9, 0.6), 1 - exit);

  return (
    <AbsoluteFill style={{ opacity }}>
      {Array.from({ length: 11 }, (_, index) => {
        const trail = Math.max(0, flight - index * 0.026);
        const tx = interpolate(trail, [0, 1], [-70, 1130]);
        const ty = 1220 - Math.sin(trail * Math.PI) * 720 - trail * 220;
        return (
          <div
            key={index}
            style={{
              position: "absolute",
              left: tx,
              top: ty,
              width: 16 - index,
              height: 16 - index,
              borderRadius: "999px",
              background: colors.accent,
              opacity: 0.25 - index * 0.018,
              filter: "blur(1px)",
            }}
          />
        );
      })}
      <div
        style={{
          position: "absolute",
          left: x,
          top: y,
          width: 30,
          height: 30,
          borderRadius: "999px",
          background: colors.ink,
          boxShadow: `0 0 34px ${colors.accent}, 0 0 90px rgba(255,90,31,.45)`,
          transform: `translate(-50%, -50%) scale(${scale})`,
        }}
      >
        <div
          style={{
            position: "absolute",
            inset: 4,
            borderRadius: "999px",
            borderTop: `2px solid ${colors.accent}`,
            borderBottom: `2px solid ${colors.accent}`,
            transform: `rotate(${frame * 8}deg)`,
          }}
        />
      </div>
    </AbsoluteFill>
  );
};

const IntroScene = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const titleIn = timed(frame, fps, 0.3, 1.0);
  const titleOut = fadeOut(frame, fps, 3.5, 0.5);
  const kickerIn = timed(frame, fps, 1.0, 0.8);

  return (
    <AbsoluteFill style={{ opacity: titleOut }}>
      <div
        style={{
          position: "absolute",
          left: 58,
          right: 58,
          top: 330,
        }}
      >
        <div
          style={{
            fontFamily: fontMono,
            color: colors.accent,
            fontSize: 25,
            fontWeight: 800,
            letterSpacing: 7,
            opacity: kickerIn,
            transform: `translateX(${interpolate(kickerIn, [0, 1], [-40, 0])}px)`,
          }}
        >
          MLB PROP INTELLIGENCE
        </div>
        <div
          style={{
            marginTop: 32,
            fontFamily: fontDisplay,
            color: colors.ink,
            fontSize: 198,
            lineHeight: 0.82,
            fontWeight: 950,
            letterSpacing: 1,
            transform: `translateY(${interpolate(titleIn, [0, 1], [90, 0])}px)`,
            opacity: titleIn,
          }}
        >
          CALL
          <br />
          YOUR
          <br />
          SHOT.
        </div>
        <div
          style={{
            marginTop: 40,
            width: 520,
            height: 5,
            background: colors.line,
          }}
        >
          <div
            style={{
              height: "100%",
              width: `${interpolate(titleIn, [0, 1], [0, 100])}%`,
              background: colors.accent,
            }}
          />
        </div>
      </div>
    </AbsoluteFill>
  );
};

const Row = ({
  pick,
  index,
}: {
  pick: (typeof picks)[number];
  index: number;
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = timed(frame, fps, 0.25 + index * 0.18, 0.75);

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "70px 1fr 150px",
        gap: 20,
        alignItems: "center",
        minHeight: 164,
        padding: "20px 22px",
        borderTop: `1px solid ${colors.line}`,
        opacity: p,
        transform: `translateX(${interpolate(p, [0, 1], [70, 0])}px)`,
      }}
    >
      <div
        style={{
          fontFamily: fontDisplay,
          color: index === 0 ? colors.accent : colors.dim,
          fontSize: 52,
          fontWeight: 900,
        }}
      >
        {pick.rank}
      </div>
      <div>
        <div
          style={{
            fontFamily: fontDisplay,
            color: colors.ink,
            fontSize: 42,
            fontWeight: 900,
            letterSpacing: 1.2,
          }}
        >
          {pick.name}
        </div>
        <div
          style={{
            marginTop: 8,
            fontFamily: fontMono,
            color: colors.dim,
            fontSize: 18,
            letterSpacing: 2,
          }}
        >
          {pick.vs} · {pick.park}
        </div>
        <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
          {pick.factors.map((factor) => (
            <div
              key={factor}
              style={{
                borderLeft: `2px solid ${colors.accent}`,
                background: "rgba(255,90,31,.07)",
                color: colors.ink,
                fontFamily: fontMono,
                fontSize: 15,
                letterSpacing: 1.3,
                padding: "9px 12px",
              }}
            >
              {factor}
            </div>
          ))}
        </div>
      </div>
      <div style={{ textAlign: "right" }}>
        <div
          style={{
            fontFamily: fontDisplay,
            color: index === 0 ? colors.accent : colors.ink,
            fontSize: 58,
            fontWeight: 950,
            lineHeight: 1,
          }}
        >
          {pick.prob}
        </div>
        <div
          style={{
            marginTop: 12,
            width: 138,
            height: 5,
            background: "rgba(255,255,255,.08)",
            marginLeft: "auto",
          }}
        >
          <div
            style={{
              width: index === 0 ? "100%" : "76%",
              height: "100%",
              background: colors.accent,
            }}
          />
        </div>
      </div>
    </div>
  );
};

const BoardScene = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const inProgress = timed(frame, fps, 0.1, 0.9);
  const out = fadeOut(frame, fps, 5.4, 0.65);

  return (
    <AbsoluteFill style={{ opacity: out }}>
      <div
        style={{
          position: "absolute",
          left: 58,
          right: 58,
          top: 260,
          border: `1px solid ${colors.line}`,
          background: "rgba(13,17,26,.9)",
          boxShadow: "0 50px 180px rgba(0,0,0,.55)",
          transform: `translateY(${interpolate(inProgress, [0, 1], [110, 0])}px) scale(${interpolate(inProgress, [0, 1], [0.95, 1])})`,
          opacity: inProgress,
        }}
      >
        <div
          style={{
            height: 86,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "0 28px",
            borderBottom: `1px solid ${colors.line}`,
            background: colors.panel2,
          }}
        >
          <div
            style={{
              display: "flex",
              gap: 14,
              alignItems: "center",
              color: colors.ink,
              fontFamily: fontMono,
              fontSize: 18,
              letterSpacing: 4,
            }}
          >
            <span style={{ color: colors.accent }}>●</span>
            TODAY&apos;S BOARD
          </div>
          <div
            style={{
              color: colors.dim,
              fontFamily: fontMono,
              fontSize: 15,
              letterSpacing: 3,
            }}
          >
            FACTORS · P(HR)
          </div>
        </div>
        {picks.map((pick, index) => (
          <Row key={pick.name} pick={pick} index={index} />
        ))}
      </div>
      <div
        style={{
          position: "absolute",
          left: 58,
          right: 58,
          bottom: 260,
          fontFamily: fontDisplay,
          color: colors.ink,
          fontSize: 82,
          fontWeight: 900,
          lineHeight: 0.95,
          opacity: timed(frame, fps, 1.15, 0.8),
        }}
      >
        THE READABLE BOARD
        <br />
        BEHIND EVERY PICK.
      </div>
    </AbsoluteFill>
  );
};

const ProofPill = ({
  label,
  value,
  delay,
}: {
  label: string;
  value: string;
  delay: number;
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = timed(frame, fps, delay, 0.7);

  return (
    <div
      style={{
        border: `1px solid ${colors.line}`,
        background: "rgba(255,255,255,.035)",
        padding: "30px 32px",
        opacity: p,
        transform: `translateY(${interpolate(p, [0, 1], [50, 0])}px)`,
      }}
    >
      <div
        style={{
          fontFamily: fontDisplay,
          color: colors.accent,
          fontSize: 86,
          fontWeight: 950,
          lineHeight: 1,
        }}
      >
        {value}
      </div>
      <div
        style={{
          marginTop: 10,
          fontFamily: fontMono,
          color: colors.dim,
          fontSize: 20,
          letterSpacing: 3,
          textTransform: "uppercase",
        }}
      >
        {label}
      </div>
    </div>
  );
};

const ProofScene = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const out = fadeOut(frame, fps, 4.0, 0.6);

  return (
    <AbsoluteFill style={{ opacity: out }}>
      <div
        style={{
          position: "absolute",
          left: 58,
          right: 58,
          top: 340,
        }}
      >
        <div
          style={{
            fontFamily: fontDisplay,
            color: colors.ink,
            fontSize: 124,
            fontWeight: 950,
            lineHeight: 0.86,
            letterSpacing: 0.5,
            opacity: timed(frame, fps, 0, 0.8),
          }}
        >
          NOT A HUNCH.
          <br />
          A MODEL.
        </div>
        <div
          style={{
            marginTop: 70,
            display: "grid",
            gap: 18,
          }}
        >
          <ProofPill value="118" label="signals per matchup" delay={0.45} />
          <ProofPill value="PARK + WX" label="conditions folded in" delay={0.75} />
          <ProofPill value="LINEUPS" label="projected plate appearances" delay={1.05} />
        </div>
      </div>
    </AbsoluteFill>
  );
};

const FinalScene = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const inProgress = timed(frame, fps, 0.05, 0.8);

  return (
    <AbsoluteFill>
      <div
        style={{
          position: "absolute",
          left: 58,
          right: 58,
          top: 420,
          opacity: inProgress,
          transform: `scale(${interpolate(inProgress, [0, 1], [0.92, 1])})`,
          transformOrigin: "left top",
        }}
      >
        <div
          style={{
            fontFamily: fontMono,
            color: colors.accent,
            fontSize: 25,
            fontWeight: 800,
            letterSpacing: 7,
          }}
        >
          OPEN THE LIVE SLATE
        </div>
        <div
          style={{
            marginTop: 32,
            fontFamily: fontDisplay,
            color: colors.ink,
            fontSize: 174,
            fontWeight: 950,
            lineHeight: 0.84,
          }}
        >
          HOMERUN
          <br />
          CALL YOUR
          <br />
          SHOT.
        </div>
        <div
          style={{
            marginTop: 58,
            display: "inline-flex",
            alignItems: "center",
            gap: 22,
            background: colors.accent,
            color: "#070707",
            padding: "24px 34px",
            fontFamily: fontMono,
            fontWeight: 900,
            fontSize: 24,
            letterSpacing: 4,
          }}
        >
          LAUNCH TODAY&apos;S BOARD
          <span style={{ fontSize: 34 }}>→</span>
        </div>
      </div>
      <div
        style={{
          position: "absolute",
          left: 58,
          right: 58,
          bottom: 58,
          fontFamily: fontBody,
          color: colors.mute,
          fontSize: 22,
          lineHeight: 1.35,
        }}
      >
        For research and entertainment. Not a sportsbook. Probabilities are model estimates, not guarantees.
      </div>
    </AbsoluteFill>
  );
};

const PromoAudio = () => {
  const { durationInFrames, fps } = useVideoConfig();

  return (
    <Audio
      src={staticFile("audio/homerun-promo-bed.wav")}
      volume={(frame) =>
        interpolate(
          frame,
          [0, sec(0.7, fps), durationInFrames - sec(1.2, fps), durationInFrames],
          [0, 0.72, 0.72, 0],
          clamp,
        )
      }
    />
  );
};

export const HomerunPromo = ({ slateDate, modelVersion }: HomerunPromoProps) => {
  const { fps } = useVideoConfig();

  return (
    <AbsoluteFill style={{ backgroundColor: colors.bg }}>
      <PromoAudio />
      <ScreenTexture />
      <BallArc />
      <Header slateDate={slateDate} modelVersion={modelVersion} />
      <Sequence from={0} durationInFrames={sec(4.2, fps)} premountFor={fps}>
        <IntroScene />
      </Sequence>
      <Sequence from={sec(3.6, fps)} durationInFrames={sec(6.3, fps)} premountFor={fps}>
        <BoardScene />
      </Sequence>
      <Sequence from={sec(9.3, fps)} durationInFrames={sec(4.9, fps)} premountFor={fps}>
        <ProofScene />
      </Sequence>
      <Sequence from={sec(13.1, fps)} durationInFrames={sec(1.9, fps)} premountFor={fps}>
        <FinalScene />
      </Sequence>
    </AbsoluteFill>
  );
};

export const PosterFrame = (props: HomerunPromoProps) => (
  <AbsoluteFill style={{ backgroundColor: colors.bg }}>
    <ScreenTexture />
    <Header {...props} />
    <IntroScene />
    <div
      style={{
        position: "absolute",
        left: 58,
        right: 58,
        bottom: 86,
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        gap: 18,
      }}
    >
      <ProofPill value="118" label="signals per matchup" delay={0} />
      <ProofPill value="15" label="games on the board" delay={0} />
    </div>
  </AbsoluteFill>
);
