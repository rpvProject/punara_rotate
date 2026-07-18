// Money/format self-check. Runs on Node >= 23.6 (built-in TS type stripping):
//   npm test   (from web/)
import assert from "node:assert/strict";
import test from "node:test";
import {
  bandColor,
  churnBandColor,
  formatINR,
  formatINRCompact,
  formatMonth,
  formatPct,
} from "../src/lib/format.ts";

test("formatINR uses Indian digit grouping on paise", () => {
  assert.equal(formatINR(12345678), "₹1,23,457"); // 123456.78 rupees, rounded
  assert.equal(formatINR(0), "₹0");
  assert.equal(formatINR(100), "₹1");
});

test("formatINRCompact uses lakh/crore", () => {
  assert.equal(formatINRCompact(940000000), "₹94.0L"); // ₹94 lakh
  assert.equal(formatINRCompact(1540000000), "₹1.5Cr");
  assert.equal(formatINRCompact(130500), "₹1.3K");
  assert.equal(formatINRCompact(9900), "₹99");
  assert.equal(formatINRCompact(-940000000), "-₹94.0L");
});

test("formatPct on 0-1 ratios", () => {
  assert.equal(formatPct(0.31), "31.0%");
  assert.equal(formatPct(1, 0), "100%");
});

test("formatMonth", () => {
  assert.equal(formatMonth("2026-06"), "Jun 26");
  assert.equal(formatMonth("garbage"), "garbage");
});

test("bandColor bands: 0-40 ember, 40-70 marigold, 70-100 teal", () => {
  assert.equal(bandColor(39.9), "#e0533d");
  assert.equal(bandColor(40), "#f2a413");
  assert.equal(bandColor(69.9), "#f2a413");
  assert.equal(bandColor(70), "#0fa284");
});

test("churnBandColor: high ember, medium marigold, low teal", () => {
  assert.equal(churnBandColor("high"), "#e0533d");
  assert.equal(churnBandColor("medium"), "#f2a413");
  assert.equal(churnBandColor("low"), "#0fa284");
});
