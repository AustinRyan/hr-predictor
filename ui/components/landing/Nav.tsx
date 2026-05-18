import Link from "next/link";

export function Nav() {
  return (
    <header className="nav">
      <Link className="logo" href="/">
        <span className="logo-mark">◆</span>
        <span className="logo-word">HOMERUN</span>
        <span className="logo-sub">/ MLB PROP INTELLIGENCE</span>
      </Link>
      <nav className="nav-links">
        <Link href="/#slate">Today&apos;s board</Link>
        <Link href="/#how">Method</Link>
        <Link href="/#model-audit">Audit</Link>
        <Link href="/model">History</Link>
        <Link href="/#app">Launch app</Link>
      </nav>
      <div className="nav-meta">
        <Link className="nav-history-link" href="/model">
          History
        </Link>
        <span className="live-dot" aria-hidden="true" />
        <span>LIVE</span>
      </div>
    </header>
  );
}
