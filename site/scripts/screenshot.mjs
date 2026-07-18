/* Full-page screenshots of the running site (npm run start -- -p 3020 -H 127.0.0.1
   must already be up). Usage: node scripts/screenshot.mjs */
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const BASE = process.env.SITE_URL || "http://127.0.0.1:3020";
const OUT = new URL("../.screenshots/", import.meta.url).pathname.replace(
  /^\/([A-Za-z]:)/,
  "$1",
);
mkdirSync(OUT, { recursive: true });

const shots = [
  { name: "mobile", width: 390, height: 844, deviceScaleFactor: 2 },
  { name: "tablet", width: 768, height: 1024, deviceScaleFactor: 1 },
  { name: "desktop", width: 1440, height: 900, deviceScaleFactor: 1 },
];

const browser = await chromium.launch();
for (const { name, width, height, deviceScaleFactor } of shots) {
  const page = await browser.newPage({
    viewport: { width, height },
    deviceScaleFactor,
  });
  await page.goto(BASE, { waitUntil: "networkidle" });
  // Let entrance transitions and lazy embeds settle.
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `${OUT}${name}.png`, fullPage: true });
  console.log(`${name}: ${width}x${height}@${deviceScaleFactor}x -> .screenshots/${name}.png`);
  await page.close();
}
await browser.close();
