import { Nav } from "@/components/landing/Nav";
import { Hero } from "@/components/landing/Hero";
import { Slate } from "@/components/landing/Slate";
import { Scoreboard } from "@/components/landing/Scoreboard";
import { Arc } from "@/components/landing/Arc";
import { How } from "@/components/landing/How";
import { Handoff } from "@/components/landing/Handoff";
import { Footer } from "@/components/landing/Footer";
import { RankingsApp } from "@/components/rankings/RankingsApp";
import { getModelMetrics, getPicksToday } from "@/lib/api";
import { adaptPicksList, extractHeroStats, type HeroStats } from "@/lib/adapters";
import type { Pick, ScoreboardGame, SlateCard } from "@/lib/mock-data";
import {
  buildScoreboard,
  buildSlate,
  buildTicker,
  countGames,
} from "@/lib/derive";

// Always fetch fresh so a "Refresh picks" cycle shows up on the next reload.
// Backend's Redis cache still absorbs repeat load (~5ms warm), so the cost
// is one fast server fetch per navigation.
export const dynamic = "force-dynamic";

export default async function HomePage() {
  const [api, metrics] = await Promise.all([
    getPicksToday({ limit: 200 }),
    getModelMetrics(),
  ]);
  const hasRealPicks = Boolean(api && api.length > 0);

  const picks: Pick[] | undefined = hasRealPicks
    ? adaptPicksList(api!)
    : undefined;
  const topStats: HeroStats | undefined = hasRealPicks
    ? extractHeroStats(api![0]!)
    : undefined;
  const scoreboardGames: ScoreboardGame[] | undefined = hasRealPicks
    ? buildScoreboard(api!)
    : undefined;
  const slateCards: SlateCard[] | undefined = hasRealPicks
    ? buildSlate(api!)
    : undefined;
  const ticker: string[] | undefined = hasRealPicks
    ? buildTicker(api!, metrics)
    : undefined;
  const gameCount = hasRealPicks ? countGames(api!) : undefined;

  return (
    <>
      <Nav />
      <main>
        <Hero
          picks={picks}
          topStats={topStats}
          ticker={ticker}
          gameCount={gameCount}
          modelVersion={metrics?.training_metadata.model_version}
          brier={metrics?.training_metrics.test_brier}
        />
        <Slate games={slateCards} />
        <Scoreboard games={scoreboardGames} />
        <Arc />
        <How />
        <Handoff />
        <RankingsApp picks={picks} />
        <Footer />
      </main>
    </>
  );
}
