import { Nav } from "@/components/landing/Nav";
import { Hero } from "@/components/landing/Hero";
import { Slate } from "@/components/landing/Slate";
import { Scoreboard } from "@/components/landing/Scoreboard";
import { Arc } from "@/components/landing/Arc";
import { How } from "@/components/landing/How";
import { Handoff } from "@/components/landing/Handoff";
import { Footer } from "@/components/landing/Footer";
import { RankingsApp } from "@/components/rankings/RankingsApp";
import { getPicksToday } from "@/lib/api";
import { adaptPicksList } from "@/lib/adapters";
import type { Pick } from "@/lib/mock-data";

export const revalidate = 300;

export default async function HomePage() {
  const api = await getPicksToday({ limit: 50 });
  const picks: Pick[] | undefined =
    api && api.length > 0 ? adaptPicksList(api) : undefined;

  return (
    <>
      <Nav />
      <main>
        <Hero picks={picks} />
        <Slate />
        <Scoreboard />
        <Arc />
        <How />
        <Handoff />
        <RankingsApp picks={picks} />
        <Footer />
      </main>
    </>
  );
}
