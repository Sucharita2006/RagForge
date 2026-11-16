import type { Metadata } from "next";
import { Fira_Sans } from "next/font/google";

import { SignBand } from "@/components/SignBand";

import "./globals.css";

const sans = Fira_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
  variable: "--font-sans",
  display: "swap",
});

export const metadata: Metadata = {
  description: "Self-hosted RAG that checks every sentence of its answers against the source.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={sans.variable}>
      <body>
        <a
          href="#content"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-ink focus:px-4 focus:py-2 focus:font-semibold focus:text-white"
        >
          Skip to content
        </a>
        <SignBand />
        <main id="content" className="mx-auto max-w-page px-4 pb-24 pt-10 sm:px-6">
          {children}
        </main>
      </body>
    </html>
  );
}
