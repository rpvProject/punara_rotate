import { Fraunces, IBM_Plex_Mono, Inter } from "next/font/google";

/* Variable Fraunces with optical-size + softness axes for editorial display. */
export const fraunces = Fraunces({
  variable: "--font-fraunces",
  subsets: ["latin"],
  axes: ["opsz", "SOFT"],
});

export const inter = Inter({ variable: "--font-inter", subsets: ["latin"] });

export const plex = IBM_Plex_Mono({
  variable: "--font-plex",
  subsets: ["latin"],
  /* 600 included so StatNum inside font-semibold never triggers synthetic
     bold (which rasterizes as a strikethrough-like smear on 1x displays). */
  weight: ["400", "500", "600"],
});

export const fontClasses = `${fraunces.variable} ${inter.variable} ${plex.variable}`;
