/**
 * Direct Postgres client for Next.js server components / route handlers.
 *
 * Previously the frontend fetched from the FastAPI backend. Now it queries
 * Postgres directly so Vercel can serve the site without a separate
 * hosted backend — the user runs inference locally and writes fresh
 * predictions into the same Neon database the deployed frontend reads.
 *
 * Connection-pool strategy: `postgres` maintains its own pool; one
 * singleton per Node process. On Vercel serverless the process is
 * short-lived so we don't worry about pool lifetime — each invocation
 * uses Neon's pooled connection string (`-pooler` in the host).
 */

import postgres, { type Sql } from "postgres";

declare global {
  var __hrp_sql: Sql | undefined;
}

function makeClient(): Sql {
  const url = process.env.DATABASE_URL;
  if (!url) {
    throw new Error(
      "DATABASE_URL is not set. Put the Postgres connection string in " +
        ".env.local locally, or set it on the Vercel project.",
    );
  }
  return postgres(url, {
    // Neon requires TLS; most self-hosted setups do too. The ?sslmode=require
    // in the URL already gates this, but the lib needs the explicit flag.
    ssl: "require",
    // Cap concurrency — Next.js SSR parallelism would otherwise burst
    // connections beyond Neon's free-tier pooler ceiling.
    max: 5,
    idle_timeout: 20,
  });
}

/** Shared postgres client. Reuses across hot-reload in dev. */
export const sql: Sql =
  globalThis.__hrp_sql ?? (globalThis.__hrp_sql = makeClient());
