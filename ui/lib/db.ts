/**
 * Neon serverless Postgres client.
 *
 * We use @neondatabase/serverless instead of the traditional `postgres`
 * library because:
 *   1. It speaks Neon's HTTP proxy (fewer connection headaches in
 *      Vercel's cold-start serverless environment — no TCP pool to
 *      warm, no SSL handshake per invocation).
 *   2. The tagged-template API is compatible with the porsager/postgres
 *      style our query modules already use, so call-sites don't change.
 *
 * In production (Vercel) `DATABASE_URL` is injected as an env var. In
 * local dev it comes from `ui/.env.local`. Either way, missing URL
 * throws loudly so `lib/api.ts::safe()` logs a real error instead of
 * silently falling back to mock data.
 */

import { neon, type NeonQueryFunction } from "@neondatabase/serverless";

type Sql = NeonQueryFunction<false, false>;

declare global {
  var __hrp_sql: Sql | undefined;
}

function makeClient(): Sql {
  const raw = process.env.DATABASE_URL;
  if (!raw) {
    throw new Error(
      "DATABASE_URL is not set. On Vercel, add it under " +
        "Project Settings → Environment Variables. Locally, put it " +
        "in ui/.env.local.",
    );
  }
  // Strip embedded whitespace. Vercel's env UI can fold long strings
  // onto multiple lines on paste; the Neon HTTP driver rejects URLs
  // with any non-printable chars because they'd break the HTTP header.
  const url = raw.replace(/\s+/g, "");
  // The Python backend uses the `postgresql+psycopg://` dialect prefix;
  // Neon's driver wants the bare `postgresql://` scheme.
  const normalized = url.replace(/^postgresql\+psycopg:\/\//, "postgresql://");
  return neon(normalized);
}

export const sql: Sql =
  globalThis.__hrp_sql ?? (globalThis.__hrp_sql = makeClient());

/** True if DATABASE_URL looks configured. Useful for /api/health. */
export function isConfigured(): boolean {
  return Boolean(process.env.DATABASE_URL);
}
