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

  const filtered: Pick[] = useMemo(() => {
    const rows = source.filter((p) => p.prob >= minProb && (team === "" || p.team === team));
    const sorted = [...rows].sort((a, b) => {
      if (sort === "prob") return b.prob - a.prob;
      if (sort === "ehr") return b.ehr - a.ehr;
      return parseEdge(b.edge) - parseEdge(a.edge);
    });
    return sorted.slice(0, limit);
  }, [source, sort, minProb, team, limit]);

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

          <div className="f-spacer" />
          <div className="f-group">
            <button type="button" className="btn btn-ghost-sm">
              <span>↻</span> REFRESH · LIVE
            </button>
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
                  return (
                    <div
                      key={p.id}
                      className={`rk-row ${rank <= 3 ? "top3" : ""}`}
                      role="button"
                      tabIndex={0}
                    >
                      <div className="rk-rank">{rank}</div>
                      <div className="rk-player">
                        <div className="rk-avatar">
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img src={headshotUrl(p.id)} alt="" />
                          <span className="rk-avatar-num">{p.num}</span>
                        </div>
                        <div>
                          <Link href={`/player/${p.id}`} className="rk-pl-name" style={{ display: "block" }}>
                            {p.first} {p.last}
                          </Link>
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
                          e.stopPropagation();
                          toggleLeg(p.id);
                        }}
                      >
                        {added ? "✓" : "+"}
                      </button>
                    </div>
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
