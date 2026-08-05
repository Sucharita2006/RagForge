import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "ragforge",
  description: "A trustworthy, self-improving RAG platform",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <nav className="flex gap-4 border-b border-neutral-200 px-8 py-3 text-sm dark:border-neutral-800">
          <Link href="/" className="font-semibold">
            ragforge
          </Link>
          <Link href="/" className="text-neutral-500 hover:text-neutral-900 dark:hover:text-neutral-100">
            Playground
          </Link>
          <Link
            href="/retrieval-inspector"
            className="text-neutral-500 hover:text-neutral-900 dark:hover:text-neutral-100"
          >
            Retrieval Inspector
          </Link>
          <Link
            href="/evaluations"
            className="text-neutral-500 hover:text-neutral-900 dark:hover:text-neutral-100"
          >
            Evaluations
          </Link>
          <Link
            href="/settings"
            className="text-neutral-500 hover:text-neutral-900 dark:hover:text-neutral-100"
          >
            Settings
          </Link>
        </nav>
        {children}
      </body>
    </html>
  );
}
