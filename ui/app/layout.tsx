import type { Metadata } from "next";
import { Archivo, Barlow_Condensed, JetBrains_Mono } from "next/font/google";
import { BootLoader } from "@/components/effects/BootLoader";
import { Chyron } from "@/components/effects/Chyron";
import { HomerunEasterEgg } from "@/components/effects/HomerunEasterEgg";
import "./globals.css";

const barlow = Barlow_Condensed({
  variable: "--font-barlow",
  weight: ["400", "500", "600", "700", "800", "900"],
  subsets: ["latin"],
  display: "swap",
});

const archivo = Archivo({
  variable: "--font-archivo",
  weight: ["400", "500", "600", "700", "800", "900"],
  subsets: ["latin"],
  display: "swap",
});

const mono = JetBrains_Mono({
  variable: "--font-mono",
  weight: ["400", "500", "600", "700"],
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Homerun — Call your shot.",
  description:
    "MLB prop intelligence. Every hitter, every pitcher, every park — graded before the first pitch.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      data-accent="clay"
      data-intensity="mid"
      className={`${barlow.variable} ${archivo.variable} ${mono.variable}`}
    >
      <body>
        <BootLoader />
        <div className="grain" aria-hidden="true" />
        <div className="scanlines" aria-hidden="true" />
        <div className="vignette" aria-hidden="true" />
        <Chyron />
        <HomerunEasterEgg />
        {children}
      </body>
    </html>
  );
}
