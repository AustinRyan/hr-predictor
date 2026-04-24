import Link from "next/link";
import { Nav } from "@/components/landing/Nav";
import { Footer } from "@/components/landing/Footer";

export default function NotFound() {
  return (
    <>
      <Nav />
      <main className="detail" style={{ display: "flex", flexDirection: "column", alignItems: "flex-start" }}>
        <span className="section-num">/ 404</span>
        <h1 className="detail-title">
          OFF THE BAT.<br />
          <span style={{ color: "var(--accent)" }}>FOUL BALL.</span>
        </h1>
        <p style={{ maxWidth: 520, marginTop: 24, color: "var(--ink-dim)", fontSize: 17, lineHeight: 1.55 }}>
          The page you&apos;re looking for doesn&apos;t exist, the player isn&apos;t
          on tonight&apos;s slate, or the matchup hasn&apos;t been graded yet.
        </p>
        <Link href="/" className="btn btn-primary" style={{ marginTop: 40 }}>
          <span>Back to the board</span>
          <span className="btn-arrow">→</span>
        </Link>
      </main>
      <Footer />
    </>
  );
}
