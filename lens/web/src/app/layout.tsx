import type { Metadata } from "next";
import { Fraunces, IBM_Plex_Mono, Inter } from "next/font/google";
import "./globals.css";
import { Nav } from "@/components/nav";

const fraunces = Fraunces({
  variable: "--font-fraunces",
  subsets: ["latin"],
  weight: ["500", "600", "700"],
});

const inter = Inter({ variable: "--font-inter", subsets: ["latin"] });

const plex = IBM_Plex_Mono({
  variable: "--font-plex",
  subsets: ["latin"],
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: "Punara Lens",
  description: "Retention intelligence — the science of the second order.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`${fraunces.variable} ${inter.variable} ${plex.variable} h-full antialiased`}
    >
      <body className="min-h-full">
        <div className="flex min-h-screen flex-col md:flex-row">
          <Nav />
          <div className="flex min-w-0 flex-1 flex-col">
            <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-10 md:px-10">
              {children}
            </main>
            <footer className="border-t border-line px-6 py-5 text-center text-xs text-graphite md:px-10">
              Every recommendation ships with a number, a baseline, and a
              deadline.
            </footer>
          </div>
        </div>
      </body>
    </html>
  );
}
