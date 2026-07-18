/** The one shared money/number formatter. Money arrives as integer paise. */

const inr = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});

const inNum = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });

/** 12345678 paise -> "₹1,23,457" (Indian digit grouping). */
export function formatINR(paise: number): string {
  return inr.format(Math.round(paise / 100));
}

/** Compact Indian notation: crore/lakh. 940000000 paise -> "₹94.0L". */
export function formatINRCompact(paise: number): string {
  const r = paise / 100;
  const sign = r < 0 ? "-" : "";
  const a = Math.abs(r);
  if (a >= 1e7) return `${sign}₹${(a / 1e7).toFixed(a >= 1e9 ? 0 : 1)}Cr`;
  if (a >= 1e5) return `${sign}₹${(a / 1e5).toFixed(a >= 1e7 ? 0 : 1)}L`;
  if (a >= 1e3) return `${sign}₹${(a / 1e3).toFixed(1)}K`;
  return `${sign}₹${inNum.format(a)}`;
}

export function formatCount(n: number): string {
  return inNum.format(n);
}

/** 0-1 ratio -> "31.0%" */
export function formatPct(rate: number, digits = 1): string {
  return `${(rate * 100).toFixed(digits)}%`;
}

/** ISO timestamp -> "2 Jun 2026"; null (no data yet) -> "—" */
export function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

/** "2026-06" -> "Jun 26" */
export function formatMonth(ym: string): string {
  const [y, m] = ym.split("-").map(Number);
  if (!y || !m) return ym;
  const names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${names[m - 1]} ${String(y).slice(2)}`;
}

/** "at_risk" -> "At risk" */
export function labelize(slug: string): string {
  const s = slug.replaceAll("_", " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** Score band per spec: 0-40 ember, 40-70 marigold, 70-100 teal. */
export function bandColor(value: number): string {
  if (value < 40) return "#e0533d";
  if (value < 70) return "#f2a413";
  return "#0fa284";
}

/** Churn-risk band -> color: high ember, medium marigold, low teal. */
export function churnBandColor(band: string): string {
  if (band === "high") return "#e0533d";
  if (band === "medium") return "#f2a413";
  return "#0fa284";
}
