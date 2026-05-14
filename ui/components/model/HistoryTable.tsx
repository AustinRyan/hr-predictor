"use client";

import { useMemo, useState } from "react";
import {
  buildDailyUnitSummaries,
  filterHistoryByDate,
  uniqueHistoryItems,
} from "@/lib/model-history-charts";
import type { PickHistoryItem } from "@/lib/types";

type Props = {
  items: readonly PickHistoryItem[];
};

function pct(v: number | null, decimals = 1): string {
  return v === null ? "-" : `${(v * 100).toFixed(decimals)}%`;
}

function american(v: number | null): string {
  if (v === null) return "-";
  return v > 0 ? `+${v}` : `${v}`;
}

function units(v: number | null): string {
  if (v === null) return "-";
  const sign = v >= 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}u`;
}

function shortDate(value: string): string {
  const [, month, day] = value.split("-");
  return `${month}/${day}`;
}

function sumSelectedUnits(items: readonly PickHistoryItem[]): number | null {
  const values = items
    .map((item) => item.settled_profit_units)
    .filter((value): value is number => value !== null);
  if (values.length === 0) return null;
  return values.reduce((total, value) => total + value, 0);
}

function tableSort(a: PickHistoryItem, b: PickHistoryItem): number {
  if (a.game_date !== b.game_date) return b.game_date.localeCompare(a.game_date);
  if (a.daily_rank !== b.daily_rank) return a.daily_rank - b.daily_rank;
  return a.batter_id - b.batter_id;
}

export function HistoryTable({ items }: Props) {
  const uniqueItems = useMemo(() => uniqueHistoryItems(items), [items]);
  const daySummaries = useMemo(
    () => buildDailyUnitSummaries(uniqueItems).sort((a, b) => b.date.localeCompare(a.date)),
    [uniqueItems],
  );
  const [selectedDate, setSelectedDate] = useState<string | null>(
    daySummaries[0]?.date ?? null,
  );
  const selectedItems = useMemo(
    () => filterHistoryByDate(uniqueItems, selectedDate).sort(tableSort),
    [selectedDate, uniqueItems],
  );
  const selectedUnits = sumSelectedUnits(selectedItems);
  const selectedExpected = selectedItems.reduce(
    (total, item) => total + item.prob_at_least_one_hr,
    0,
  );
  const selectedHits = selectedItems.filter((item) => item.actual_hr).length;
  const selectedWithOdds = selectedItems.filter(
    (item) => item.settled_profit_units !== null,
  ).length;

  if (uniqueItems.length === 0) {
    return (
      <div className="detail-card">
        <div className="detail-card-k">NO SETTLED TOP PICKS YET</div>
        <div className="detail-card-v small">
          This fills after predictions and next-day Statcast results exist for the same model version.
        </div>
      </div>
    );
  }

  return (
    <section className="history-table-panel">
      <div className="history-day-strip" aria-label="Filter history by day">
        <button
          type="button"
          className={selectedDate === null ? "active" : ""}
          onClick={() => setSelectedDate(null)}
        >
          <span>ALL DAYS</span>
          <b>{uniqueItems.length} picks</b>
        </button>
        {daySummaries.map((day) => (
          <button
            key={day.date}
            type="button"
            className={selectedDate === day.date ? "active" : ""}
            onClick={() => setSelectedDate(day.date)}
          >
            <span>{shortDate(day.date)}</span>
            <b className={(day.settledProfitUnits ?? 0) >= 0 ? "pos" : "neg"}>
              {units(day.settledProfitUnits)}
            </b>
          </button>
        ))}
      </div>

      <div className="history-table-summary">
        <div>
          <span>{selectedDate ?? "ALL DAYS"}</span>
          <b>{selectedItems.length} picks</b>
        </div>
        <div>
          <span>DAY UNITS</span>
          <b className={(selectedUnits ?? 0) >= 0 ? "pos" : "neg"}>{units(selectedUnits)}</b>
        </div>
        <div>
          <span>HITS</span>
          <b>{selectedHits}</b>
        </div>
        <div>
          <span>EXPECTED</span>
          <b>{selectedExpected.toFixed(2)}</b>
        </div>
        <div>
          <span>ODDS ROWS</span>
          <b>{selectedWithOdds}</b>
        </div>
      </div>

      <div className="history-table-scroll">
        <table className="history-table">
          <colgroup>
            <col className="history-col-date" />
            <col className="history-col-rank" />
            <col className="history-col-player" />
            <col className="history-col-prob" />
            <col className="history-col-result" />
            <col className="history-col-book" />
            <col className="history-col-money" />
          </colgroup>
          <thead>
            <tr>
              <th>DATE</th>
              <th>RANK</th>
              <th>BATTER</th>
              <th>P(HR)</th>
              <th>RESULT</th>
              <th>BOOK</th>
              <th>P/L</th>
            </tr>
          </thead>
          <tbody>
            {selectedItems.map((item) => (
              <tr
                className={item.actual_hr ? "history-row-hit" : "history-row-miss"}
                key={`${item.game_date}-${item.game_pk}-${item.batter_id}`}
              >
                <td className="history-date-cell" data-label="Date">
                  {item.game_date}
                </td>
                <td className="history-rank-cell" data-label="Rank">
                  <span>#{item.daily_rank}</span>
                </td>
                <td className="history-table-player" data-label="Batter">
                  <b className="history-player-main">
                    {(item.batter_name ?? `#${item.batter_id}`).toUpperCase()}
                  </b>
                  <div className="history-player-meta">
                    {item.team_abbr ?? "-"} / VS {(item.pitcher_name ?? "TBD").toUpperCase()}
                  </div>
                </td>
                <td className="history-number-cell" data-label="P(HR)">
                  {pct(item.prob_at_least_one_hr, 2)}
                </td>
                <td data-label="Result">
                  <span className={`history-result-pill ${item.actual_hr ? "pos" : "miss"}`}>
                    {item.actual_hr ? `${item.actual_hrs} HR` : "MISS"}
                  </span>
                </td>
                <td className="history-book-cell" data-label="Book">
                  {item.odds_bookmaker
                    ? `${item.odds_bookmaker} ${american(item.odds_price_american)}`
                    : "-"}
                </td>
                <td data-label="P/L">
                  <span
                    className={`history-money-pill ${
                      (item.settled_profit_units ?? 0) >= 0 ? "pos" : "neg"
                    }`}
                  >
                    {units(item.settled_profit_units)}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="history-table-note">
        Real settled rows only. Duplicate refreshes are collapsed by game, date, and batter.
      </div>
    </section>
  );
}
