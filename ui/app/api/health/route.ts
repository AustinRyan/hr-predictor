/**
 * GET /api/health — connectivity probe for the live deploy.
 *
 * Returns JSON that makes the deploy's actual state visible so the user
 * (or I) can curl the endpoint and see whether the DB env var is set,
 * whether Neon is reachable, and whether there are actually predictions
 * to render. If the site shows no data, this route pinpoints why.
 *
 * Safe to expose publicly: only returns shape + counts, no row data.
 */

import { NextResponse } from "next/server";
import { isConfigured, sql } from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET() {
  const raw = process.env.DATABASE_URL ?? "";
  const env = {
    DATABASE_URL_set: isConfigured(),
    DATABASE_URL_length: raw.length,
    DATABASE_URL_has_whitespace: /\s/.test(raw),
    NEXT_PUBLIC_ALLOW_REFRESH: process.env.NEXT_PUBLIC_ALLOW_REFRESH ?? null,
    node_env: process.env.NODE_ENV ?? null,
    vercel_env: process.env.VERCEL_ENV ?? null,
  };

  if (!env.DATABASE_URL_set) {
    return NextResponse.json(
      {
        ok: false,
        stage: "env",
        reason: "DATABASE_URL not set on this deployment",
        env,
      },
      { status: 500 },
    );
  }

  try {
    const counts = (await sql`
      SELECT
        (SELECT COUNT(*)::int FROM predictions) AS predictions,
        (SELECT COUNT(*)::int FROM daily_schedule) AS daily_schedule,
        (SELECT COUNT(*)::int FROM players) AS players,
        (SELECT COUNT(*)::int FROM matchup_features) AS matchup_features,
        (SELECT MAX(game_date)::text FROM predictions) AS latest_prediction_date
    `) as unknown as Array<{
      predictions: number;
      daily_schedule: number;
      players: number;
      matchup_features: number;
      latest_prediction_date: string | null;
    }>;
    return NextResponse.json({
      ok: true,
      stage: "db",
      env,
      counts: counts[0] ?? null,
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return NextResponse.json(
      {
        ok: false,
        stage: "db_query",
        reason: msg,
        env,
      },
      { status: 500 },
    );
  }
}
