"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { PICKS, TEAMS, headshotUrl, type Pick } from "@/lib/mock-data";
import { Ticket } from "./Ticket";

type SortKey = "prob" | "ehr" | "edge";

function parseEdge(e: string): number {
  return parseFloat(e.replace("+", ""));
}

type RankingsProps = {
  picks?: readonly Pick[];
};

export function RankingsApp({ picks }: RankingsProps = {}) {
  const source: readonly Pick[] = picks && picks.length > 0 ? picks : PICKS;

  const [sort, setSort] = useState<SortKey>("prob");
  const [minProb, setMinProb] = useState<number>(3.0);
  const [team, setTeam] = useState<string>("");
  const [limit, setLimit] = useState<number>(20);
  const [parlay, setParlay] = useState<number[]>([]);
  const [locked, setLocked] = useState<boolean>(false);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [refreshPhase, setRefreshPhase] = useState<string>("");
  const [onePerGame, setOnePerGame] = useState<boolean>(false);

  const filtered: Pick[] = useMemo(() => {
    const rows = source.filter((p) => p.prob >= minProb && (team === "" || p.team === team));
    const sorted = [...rows].sort((a, b) => {
      if (sort === "prob") return b.prob - a.prob;
      if (sort === "ehr") return b.ehr - a.ehr;
      return parseEdge(b.edge) - parseEdge(a.edge);
    });
    // "One per game": park + wind are shared across every batter in a
    // game, so top-N often clusters in the best 1-2 parks. When enabled,
    // keep only the highest-prob pick for each game_pk so the list
    // diversifies across the slate (prop-bet friendlier).
    if (onePerGame) {
      const seen = new Set<number>();
      const diversified: Pick[] = [];
      for (const p of sorted) {
        const key = p.gamePk ?? -1;
        if (key === -1 || seen.has(key)) continue;
        seen.add(key);
        diversified.push(p);
      }
      return diversified.slice(0, limit);
    }
    return sorted.slice(0, limit);
  }, [source, sort, minProb, team, limit, onePerGame]);

  const parlayLegs = source.filter((p) => parlay.includes(p.id));
  const combinedP = parlayLegs.reduce((acc, p) => acc * (p.prob / 100), 1);
  const fairOdds =
    parlayLegs.length === 0
      ? "—"
      : combinedP >= 0.5
        ? `${Math.round(-100 / (1 / combinedP - 1))}`
        : `+${Math.round((1 / combinedP - 1) * 100)}`;
  const pays = parlayLegs.length === 0 ? "—" : `$${Math.round(100 / combinedP)}`;

  function toggleLeg(id: number): void {
    setParlay((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  async function runRefresh(): Promise<void> {
    if (refreshing) return;
    setRefreshing(true);
    setRefreshPhase("STARTING");
    const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8765";
    try {
      const start = await fetch(`${base}/admin/refresh-picks`, { method: "POST" });
      if (!start.ok) {
        const msg = start.status === 409 ? "REFRESH ALREADY RUNNING" : `HTTP ${start.status}`;
        throw new Error(msg);
      }
      // Poll status every 1.2s until done/error
      for (;;) {
        await new Promise((r) => setTimeout(r, 1200));
        const sr = await fetch(`${base}/admin/refresh-status`, { cache: "no-store" });
        if (!sr.ok) throw new Error(`status ${sr.status}`);
        const s = (await sr.json()) as {
          status: string;
          phase: string | null;
          error: string | null;
          rows_written: number | null;
        };
        setRefreshPhase((s.phase ?? s.status).toUpperCase());
        if (s.status === "done") {
          setRefreshPhase(`DONE · ${s.rows_written ?? 0} ROWS`);
          break;
        }
        if (s.status === "error") {
          throw new Error(s.error ?? "unknown error");
        }
      }
      // Give user a moment to see the DONE state before reload
      await new Promise((r) => setTimeout(r, 700));
      window.location.reload();
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      console.error("refresh failed", err);
      setRefreshPhase("ERROR");
      // Surface the real reason to the user (e.g. "lineups not yet
      // published"). Browser alert is crude but guaranteed visible.
      window.alert(`Refresh failed: ${msg}`);
      await new Promise((r) => setTimeout(r, 1200));
      setRefreshing(false);
      setRefreshPhase("");
    }
  }

  return (
    <section className="app" id="app">
      <div className="app-shell">
        <div className="app-bar">
          <div className="app-bar-l">
            <span className="app-dot" aria-hidden="true" />
            <span className="app-title">TODAY&apos;S BOARD</span>
            <span className="app-sep">/</span>
            <span>LIVE SLATE</span>
          </div>
          <div className="app-bar-c">
            <button className="tab active" type="button">Rankings</button>
            <button className="tab" type="button">Parlays</button>
            <button className="tab" type="button">Model</button>
          </div>
          <div className="app-bar-r">
            <span>MODEL v4.2.1</span>
            <span className="app-sep">·</span>
            <span>BRIER .0043</span>
          </div>
        </div>

        <div className="filters">
          <div className="f-group">
            <label className="f-label">SORT</label>
            <div className="seg">
              {(["prob", "ehr", "edge"] as const).map((k) => (
                <button
                  key={k}
                  type="button"
                  className={`seg-btn ${sort === k ? "active" : ""}`}
                  onClick={() => setSort(k)}
                >
                  {k === "prob" ? "Probability" : k === "ehr" ? "E[HR]" : "Book edge"}
                </button>
              ))}
            </div>
          </div>

          <div className="f-group">
            <label className="f-label">MIN P(HR)</label>
            <div className="slider-wrap">
              <input
                type="range"
                min={0}
                max={15}
                step={0.5}
                value={minProb}
                onChange={(e) => setMinProb(parseFloat(e.target.value))}
                aria-label="Minimum probability"
              />
              <div className="slider-val">{minProb.toFixed(1)}%</div>
            </div>
          </div>

          <div className="f-group">
            <label className="f-label">TEAM</label>
            <select
              className="select"
              value={team}
              onChange={(e) => setTeam(e.target.value)}
              aria-label="Team filter"
            >
              <option value="">ALL · 30 TEAMS</option>
              {[...TEAMS].sort().map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>

          <div className="f-group">
            <label className="f-label">SHOW</label>
            <div className="seg">
              {[10, 20, 50].map((n) => (
                <button
                  key={n}
                  type="button"
                  className={`seg-btn ${limit === n ? "active" : ""}`}
                  onClick={() => setLimit(n)}
                >
                  {n}
                </button>
              ))}
            </div>
          </div>

          <div className="f-group">
            <label className="f-label">DIVERSIFY</label>
            <div className="seg">
              <button
                type="button"
                className={`seg-btn ${!onePerGame ? "active" : ""}`}
                onClick={() => setOnePerGame(false)}
                title="Raw ranking — can cluster in hitter-friendly games"
              >
                ALL
              </button>
              <button
                type="button"
                className={`seg-btn ${onePerGame ? "active" : ""}`}
                onClick={() => setOnePerGame(true)}
                title="One best pick per game — spread across the slate"
              >
                1 / GAME
              </button>
            </div>
          </div>

          <div className="f-spacer" />
          <div className="f-group">
            {process.env.NEXT_PUBLIC_ALLOW_REFRESH === "true" && (
              <button
                type="button"
                className="btn btn-ghost-sm"
                onClick={() => void runRefresh()}
                disabled={refreshing}
                title="Re-run the daily ingest + inference pipeline on the local backend"
              >
                <span style={{ display: "inline-block", animation: refreshing ? "spin 1.2s linear infinite" : undefined }}>↻</span>{" "}
                {refreshing ? refreshPhase || "REFRESHING" : "REFRESH PICKS"}
              </button>
            )}
          </div>
        </div>

        <div className="app-body">
          <div className="rankings">
            <div className="rk-head">
              <div className="rk-c rk-c-rank">#</div>
              <div className="rk-c rk-c-player">PLAYER</div>
              <div className="rk-c rk-c-match">MATCHUP</div>
              <div className="rk-c rk-c-ctx">CTX</div>
              <div className="rk-c rk-c-prob">P(HR)</div>
              <div className="rk-c rk-c-ehr">E[HR]</div>
              <div className="rk-c rk-c-edge">EDGE</div>
              <div className="rk-c rk-c-add" />
            </div>
            <div className="rk-body">
              {filtered.length === 0 ? (
                <div className="parlay-empty" style={{ padding: "80px 20px" }}>
                  <div className="pe-icon">◆</div>
                  <div className="pe-text">
                    No picks match your filters.<br />
                    Loosen the minimum, or change the team.
                  </div>
                </div>
              ) : (
                filtered.map((p, i) => {
                  const rank = i + 1;
                  const edgeNeg = p.neg || p.edge.startsWith("-");
                  const added = parlay.includes(p.id);
                  const matchupHref = p.gamePk
                    ? `/matchup/${p.gamePk}/${p.id}`
                    : `/player/${p.id}`;
                  return (
                    <Link
                      key={p.id}
                      href={matchupHref}
                      className={`rk-row ${rank <= 3 ? "top3" : ""}`}
                      aria-label={`View full breakdown for ${p.first} ${p.last}`}
                    >
                      <div className="rk-rank">{rank}</div>
                      <div className="rk-player">
                        <div className="rk-avatar">
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img src={headshotUrl(p.id)} alt="" />
                          {p.num > 0 && <span className="rk-avatar-num">{p.num}</span>}
                        </div>
                        <div>
                          <div className="rk-pl-name">{p.first} {p.last}</div>
                          <div className="rk-pl-meta">
                            <span className="rk-team">{p.team}</span>
                            <span>{p.pos}</span>
                            <span>·</span>
                            <span>{p.hand}</span>
                          </div>
                        </div>
                      </div>
                      <div className="rk-match">
                        <div className="rk-match-top">vs {p.vs}</div>
                        <div className="rk-match-bot">{p.park} · {p.time}</div>
                      </div>
                      <div className="rk-ctx">
                        {p.ctx.map((c, j) => (
                          <span
                            key={j}
                            className={`rk-ctx-chip ${c.pos ? "pos" : ""} ${c.neg ? "neg" : ""}`}
                          >
                            {c.k} {c.v}
                          </span>
                        ))}
                      </div>
                      <div className="rk-prob">
                        <div className="rk-prob-pct">{p.prob.toFixed(1)}%</div>
                        <div className="rk-prob-bar">
                          <span style={{ width: `${Math.min(100, p.prob * 5)}%` }} />
                        </div>
                      </div>
                      <div className="rk-ehr">{p.ehr.toFixed(3)}</div>
                      <div className={`rk-edge ${edgeNeg ? "neg" : "pos"}`}>{p.edge}</div>
                      <button
                        type="button"
                        className={`rk-add ${added ? "added" : ""}`}
                        aria-label={added ? "Remove from parlay" : "Add to parlay"}
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          toggleLeg(p.id);
                        }}
                      >
                        {added ? "✓" : "+"}
                      </button>
                    </Link>
                  );
                })
              )}
            </div>
          </div>

          <aside className={`parlay ${locked ? "locked" : ""}`}>
            <div className="parlay-head">
              <span>BUILD PARLAY</span>
              <span className="parlay-count">{parlayLegs.length} legs</span>
            </div>

            {parlayLegs.length === 0 ? (
              <div className="parlay-empty">
                <div className="pe-icon">◆</div>
                <div className="pe-text">
                  Add legs from the board.<br />
                  Combined odds update live.
                </div>
              </div>
            ) : (
              <div className="parlay-legs" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {parlayLegs.map((leg) => (
                  <div
                    key={leg.id}
                    style={{
                      background: "var(--bg-2)",
                      border: "1px solid var(--line)",
                      padding: 10,
                      display: "grid",
                      gridTemplateColumns: "1fr auto",
                      gap: 6,
                    }}
                  >
                    <div>
                      <div style={{
                        fontFamily: "var(--f-display)",
                        fontWeight: 700,
                        fontSize: 13,
                        letterSpacing: ".06em",
                        textTransform: "uppercase",
                      }}>
                        {leg.first} {leg.last}
                      </div>
                      <div style={{
                        fontFamily: "var(--f-mono)",
                        fontSize: 10,
                        letterSpacing: ".12em",
                        color: "var(--ink-mute)",
                        textTransform: "uppercase",
                        marginTop: 2,
                      }}>
                        vs {leg.vs}
                      </div>
                    </div>
                    <div style={{
                      fontFamily: "var(--f-display)",
                      fontWeight: 800,
                      fontSize: 18,
                      color: "var(--accent)",
                      fontVariantNumeric: "tabular-nums",
                      alignSelf: "center",
                    }}>
                      {leg.prob.toFixed(1)}%
                    </div>
                    <button
                      type="button"
                      onClick={() => toggleLeg(leg.id)}
                      style={{
                        gridColumn: "1 / -1",
                        fontFamily: "var(--f-mono)",
                        fontSize: 10,
                        letterSpacing: ".14em",
                        color: "var(--ink-mute)",
                        textAlign: "right",
                        textTransform: "uppercase",
                      }}
                    >
                      remove
                    </button>
                  </div>
                ))}
              </div>
            )}

            <div className="parlay-summary">
              <div className="ps-row">
                <span>Combined P</span>
                <span>{parlayLegs.length === 0 ? "—" : `${(combinedP * 100).toFixed(2)}%`}</span>
              </div>
              <div className="ps-row">
                <span>Fair odds</span>
                <span>{fairOdds}</span>
              </div>
              <div className="ps-row big">
                <span>$100 pays</span>
                <span className="accent">{pays}</span>
              </div>
              <button
                type="button"
                className="btn btn-primary btn-full"
                disabled={parlayLegs.length < 2}
                onClick={() => setLocked(true)}
              >
                LOCK PARLAY
              </button>
              <button
                type="button"
                className="btn-text"
                onClick={() => setParlay([])}
              >
                clear all
              </button>
            </div>

            {locked && (
              <Ticket
                legs={parlayLegs}
                combinedP={combinedP}
                pays={pays}
                onReset={() => {
                  setLocked(false);
                  setParlay([]);
                }}
              />
            )}
          </aside>
        </div>
      </div>
    </section>
  );
}
