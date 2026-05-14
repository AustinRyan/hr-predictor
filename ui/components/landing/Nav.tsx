export function Nav() {
  return (
    <header className="nav">
      <a className="logo" href="#top">
        <span className="logo-mark">◆</span>
        <span className="logo-word">HOMERUN</span>
        <span className="logo-sub">/ MLB PROP INTELLIGENCE</span>
      </a>
      <nav className="nav-links">
        <a href="#slate">Today&apos;s board</a>
        <a href="#how">Method</a>
        <a href="#model-audit">Audit</a>
        <a href="/model">History</a>
        <a href="#app">Launch app</a>
      </nav>
      <div className="nav-meta">
        <span className="live-dot" aria-hidden="true" />
        <span>LIVE</span>
      </div>
    </header>
  );
}
