"use client";

import { Check, ChevronDown, ExternalLink, Plus } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import {
  headshotUrl,
  type FactorGroup,
  type FactorItem,
  type Pick,
} from "@/lib/pick-view";
import { boardSortLabel, sortPicksForBoard, type SortKey } from "@/lib/ranking-sort";
import { Ticket } from "./Ticket";

type FactorSignal = {
  group: string;
  item: FactorItem;
};

type RankingsProps = {
  picks?: readonly Pick[];
};

const EMPTY_PICKS: readonly Pick[] = [];

function fallbackFactors(p: Pick): FactorGroup[] {
  return [
    {
      label: "READ",
      items: p.ctx.map((c) => ({
        label: c.k,
        value: c.v,
        tone: c.pos ? "up" : c.neg ? "down" : "neutral",
      })),
    },
    {
      label: "MODEL",
      items: [
        { label: "EHR", value: p.ehr.toFixed(3), tone: "neutral" },
        { label: "LIFT", value: p.edge, tone: p.edge.startsWith("-") ? "down" : "up" },
      ],
    },
  ];
}

function primaryFactor(group: FactorGroup): FactorItem | null {
  const preferred: Record<string, string[]> = {
    BAT: ["BRL", "EV90", "EHR"],
    MATCH: ["SP HR/9", "SP BRL", "HAND"],
    "PARK/WX": ["PARK", "WIND CF", "TEMP"],
    MARKET: ["EDGE", "BOOK", "FAIR", "EV"],
    MODEL: [],
  };
  const labels = preferred[group.label] ?? [];
  for (const label of labels) {
    const item = group.items.find((candidate) => candidate.label === label);
    if (item) return item;
  }
  return group.items.find((item) => item.tone === "up") ?? group.items[0] ?? null;
}

function summarySignals(groups: FactorGroup[]): FactorSignal[] {
  const preferredOrder = ["MARKET", "BAT", "MATCH", "PARK/WX"];
  const orderedGroups = [
    ...preferredOrder
      .map((label) => groups.find((group) => group.label === label))
      .filter((group): group is FactorGroup => Boolean(group)),
    ...groups.filter((group) => !preferredOrder.includes(group.label)),
  ];

  return orderedGroups.slice(0, 4).flatMap((group) => {
    const item = primaryFactor(group);
    return item ? [{ group: group.label, item }] : [];
  });
}

function signalGroupLabel(label: string): string {
  return label === "PARK/WX" ? "PARK" : label;
}

export function RankingsApp({ picks }: RankingsProps = {}) {
  const source: readonly Pick[] = picks ?? EMPTY_PICKS;

  const [sort, setSort] = useState<SortKey>("prob");
  const [minProb, setMinProb] = useState<number>(3.0);
  const [team, setTeam] = useState<string>("");
  const [limit, setLimit] = useState<number>(20);
  const [parlay, setParlay] = useState<number[]>([]);
  const [locked, setLocked] = useState<boolean>(false);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [refreshPhase, setRefreshPhase] = useState<string>("");
  const [onePerGame, setOnePerGame] = useState<boolean>(false);
  const [expandedRows, setExpandedRows] = useState<Set<string>>(() => new Set());

  const filtered: Pick[] = useMemo(() => {
    return sortPicksForBoard(source, {
      sort,
      minProb,
      team,
      limit,
      onePerGame,
    });
  }, [source, sort, minProb, team, limit, onePerGame]);

  const teamOptions = useMemo(
    () => [...new Set(source.map((p) => p.team).filter((t) => t && t !== "—"))].sort(),
    [source],
  );

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

  function toggleExpanded(rowId: string): void {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(rowId)) next.delete(rowId);
      else next.add(rowId);
      return next;
    });
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
          <div className="f-group f-group-sort">
            <label className="f-label">SORT</label>
            <div className="seg">
              {(["prob", "ehr", "edge"] as const).map((k) => (
                <button
                  key={k}
                  type="button"
                  className={`seg-btn ${sort === k ? "active" : ""}`}
                  aria-pressed={sort === k}
                  data-sort-key={k}
                  onClick={() => setSort(k)}
                >
                  {boardSortLabel(k)}
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
              <option value="">ALL TEAMS</option>
              {teamOptions.map((t) => (
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

        <div className="mobile-sort-status" aria-live="polite">
          <span>Sorted by</span>
          <b>{boardSortLabel(sort)}</b>
          {filtered[0] && (
            <span>
              Top {filtered[0].last} · {sort === "prob"
                ? `${filtered[0].prob.toFixed(1)}%`
                : sort === "ehr"
                  ? filtered[0].ehr.toFixed(3)
                  : filtered[0].edge}
            </span>
          )}
        </div>

        <div className="app-body">
          <div className="rankings">
            <div className="rk-head">
              <div className="rk-c rk-c-rank">#</div>
              <div className="rk-c rk-c-player">PLAYER</div>
              <div className="rk-c rk-c-match">MATCHUP</div>
              <div className="rk-c rk-c-factors">FACTORS</div>
              <div className="rk-c rk-c-prob">P(HR)</div>
              <div className="rk-c rk-c-add" />
            </div>
            <div className="rk-body">
              {filtered.length === 0 ? (
                <div className="parlay-empty" style={{ padding: "80px 20px" }}>
                  <div className="pe-icon">◆</div>
                  <div className="pe-text">
                    {source.length === 0 ? (
                      <>
                        No live picks loaded.<br />
                        Run the refresh pipeline or check the database connection.
                      </>
                    ) : (
                      <>
                        No picks match your filters.<br />
                        Loosen the minimum, or change the team.
                      </>
                    )}
                  </div>
                </div>
              ) : (
                filtered.map((p, i) => {
                  const rank = i + 1;
                  const edgeNeg = p.neg || p.edge.startsWith("-");
                  const added = parlay.includes(p.id);
                  const rowId = `${p.gamePk ?? "player"}-${p.id}`;
                  const expanded = expandedRows.has(rowId);
                  const matchupHref = p.gamePk
                    ? `/matchup/${p.gamePk}/${p.id}`
                    : `/player/${p.id}`;
                  const factorGroups = p.factors && p.factors.length > 0 ? p.factors : fallbackFactors(p);
                  const signals = summarySignals(factorGroups);
                  return (
                    <article
                      key={rowId}
                      className={`rk-row ${rank <= 3 ? "top3" : ""} ${expanded ? "expanded" : ""}`}
                    >
                      <div className="rk-rank">{rank}</div>
                      <Link
                        href={matchupHref}
                        className="rk-player rk-player-link"
                        aria-label={`View full breakdown for ${p.first} ${p.last}`}
                      >
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
                      </Link>
                      <Link href={matchupHref} className="rk-match rk-match-link">
                        <div className="rk-match-top">vs {p.vs}</div>
                        <div className="rk-match-bot">{p.park} · {p.time}</div>
                      </Link>
                      <div className="rk-factor-summary">
                        {signals.map(({ group, item }) => (
                          <div
                            className={`rk-signal ${item.tone ?? "neutral"}`}
                            key={`${group}-${item.label}-${item.value}`}
                          >
                            <span className="rk-signal-group">{signalGroupLabel(group)}</span>
                            <span className="rk-signal-value">
                              <b>{item.value}</b>
                              <span>{item.label}</span>
                            </span>
                          </div>
                        ))}
                      </div>
                      <div className="rk-prob">
                        <div className="rk-prob-pct">{p.prob.toFixed(1)}%</div>
                        <div className="rk-prob-bar">
                          <span style={{ width: `${Math.min(100, p.prob * 5)}%` }} />
                        </div>
                        <div className="rk-prob-sub">
                          <span>E {p.ehr.toFixed(3)}</span>
                          <span className={edgeNeg ? "neg" : "pos"}>{p.edgeLabel ?? "LIFT"} {p.edge}</span>
                        </div>
                        {p.bookOdds && p.fairOdds && (
                          <div className="rk-odds-sub">
                            <span>{p.bookOdds}</span>
                            <span>fair {p.fairOdds}</span>
                            {p.ev && <span className={p.ev.startsWith("-") ? "neg" : "pos"}>EV {p.ev}</span>}
                          </div>
                        )}
                      </div>
                      <div className="rk-actions">
                        <button
                          type="button"
                          className={`rk-detail-toggle ${expanded ? "open" : ""}`}
                          aria-label={expanded ? "Hide factors" : "Show all factors"}
                          aria-expanded={expanded}
                          aria-controls={`rk-detail-${rowId}`}
                          onClick={() => toggleExpanded(rowId)}
                        >
                          <ChevronDown size={16} strokeWidth={2.4} />
                        </button>
                        <button
                          type="button"
                          className={`rk-add ${added ? "added" : ""}`}
                          aria-label={added ? "Remove from parlay" : "Add to parlay"}
                          onClick={() => toggleLeg(p.id)}
                        >
                          {added ? <Check size={15} strokeWidth={2.6} /> : <Plus size={16} strokeWidth={2.5} />}
                        </button>
                      </div>
                      {expanded && (
                        <div className="rk-detail" id={`rk-detail-${rowId}`}>
                          <div className="rk-detail-groups">
                            {factorGroups.map((group) => (
                              <section className="rk-detail-group" key={group.label}>
                                <div className="rk-detail-label">{group.label}</div>
                                <div className="rk-detail-items">
                                  {group.items.map((item) => (
                                    <div
                                      className={`rk-detail-item ${item.tone ?? "neutral"}`}
                                      key={`${group.label}-${item.label}-${item.value}`}
                                    >
                                      <span>{item.label}</span>
                                      <b>{item.value}</b>
                                    </div>
                                  ))}
                                </div>
                              </section>
                            ))}
                          </div>
                          <Link href={matchupHref} className="rk-detail-link">
                            <ExternalLink size={14} strokeWidth={2.4} />
                            Breakdown
                          </Link>
                        </div>
                      )}
                    </article>
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
