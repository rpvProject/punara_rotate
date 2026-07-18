"use client";

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { TooltipContentProps } from "recharts";
import type { RevenueMonth, ScoreHistoryPoint } from "@/lib/api";
import { bandColor, formatINRCompact, formatMonth, formatPct } from "@/lib/format";

// brand chart constants — teal/blue pair validated for CVD on Nightfall
const TEAL = "#0fa284";
const NEW_BLUE = "#5b7fd9";
const MARIGOLD = "#f2a413";
const AXIS = "#5a6272";
const GRID = "#232b3d";

const axisProps = {
  stroke: AXIS,
  tickLine: false,
  axisLine: { stroke: GRID },
  tick: { fill: "#9aa3b5", fontSize: 11, fontFamily: "var(--font-plex)" },
} as const;

function Tip({
  active,
  payload,
  label,
  fmt,
}: TooltipContentProps & { fmt: (v: number) => string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="num rounded border border-line bg-nightfall/95 px-3 py-2 text-xs shadow-lg">
      <div className="mb-1 text-graphite">{String(label)}</div>
      {payload.map((p) => (
        <div key={String(p.dataKey)} className="flex items-center gap-2 py-0.5">
          <span
            className="inline-block h-2 w-2 rounded-[2px]"
            style={{ background: p.color }}
          />
          <span className="text-muted">{p.name}</span>
          <span className="ml-auto pl-4 text-bone">{fmt(Number(p.value))}</span>
        </div>
      ))}
    </div>
  );
}

/** Overview sparkline: monthly revenue, single teal series. */
export function RevenueSparkline({ data }: { data: RevenueMonth[] }) {
  const rows = data.map((m) => ({ month: formatMonth(m.month), revenue: m.revenue_paise }));
  return (
    <ResponsiveContainer width="100%" height={64}>
      <AreaChart data={rows} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id="spark" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={TEAL} stopOpacity={0.35} />
            <stop offset="100%" stopColor={TEAL} stopOpacity={0} />
          </linearGradient>
        </defs>
        <Tooltip
          content={(p: TooltipContentProps) => (
            <Tip {...p} fmt={formatINRCompact} />
          )}
        />
        <Area
          type="monotone"
          dataKey="revenue"
          name="Revenue"
          stroke={TEAL}
          strokeWidth={2}
          fill="url(#spark)"
          dot={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

/** Monthly revenue, stacked new vs repeat. One axis — the repeat-rate line
 *  lives in its own chart below (never dual-axis). */
export function RevenueStack({ data }: { data: RevenueMonth[] }) {
  const rows = data.map((m) => ({
    month: formatMonth(m.month),
    New: m.revenue_paise - m.repeat_revenue_paise,
    Repeat: m.repeat_revenue_paise,
  }));
  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 8 }} barCategoryGap="25%">
        <CartesianGrid stroke={GRID} vertical={false} strokeDasharray="0" />
        <XAxis dataKey="month" {...axisProps} interval="preserveStartEnd" />
        <YAxis {...axisProps} tickFormatter={formatINRCompact} width={64} />
        <Tooltip
          cursor={{ fill: "rgba(250,247,240,0.04)" }}
          content={(p: TooltipContentProps) => (
            <Tip {...p} fmt={formatINRCompact} />
          )}
        />
        {/* 2px surface gap between stacked segments via stroke */}
        <Bar dataKey="New" stackId="rev" fill={NEW_BLUE} stroke="#101623" strokeWidth={1} />
        <Bar
          dataKey="Repeat"
          stackId="rev"
          fill={TEAL}
          stroke="#101623"
          strokeWidth={1}
          radius={[3, 3, 0, 0]}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function RepeatRateLine({ data }: { data: RevenueMonth[] }) {
  const rows = data.map((m) => ({ month: formatMonth(m.month), rate: m.repeat_rate }));
  return (
    <ResponsiveContainer width="100%" height={180}>
      <LineChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="month" {...axisProps} interval="preserveStartEnd" />
        <YAxis
          {...axisProps}
          tickFormatter={(v: number) => formatPct(v, 0)}
          width={48}
          domain={[0, (max: number) => Math.min(1, max * 1.3)]}
        />
        <Tooltip
          content={(p: TooltipContentProps) => (
            <Tip {...p} fmt={(v) => formatPct(v)} />
          )}
        />
        <Line
          type="monotone"
          dataKey="rate"
          name="Repeat rate"
          stroke={MARIGOLD}
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 4 }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function ScoreHistoryLine({ data }: { data: ScoreHistoryPoint[] }) {
  const rows = data.map((p) => ({
    at: new Date(p.computed_at).toLocaleDateString("en-IN", {
      month: "short",
      year: "2-digit",
      timeZone: "UTC",
    }),
    value: p.value,
  }));
  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="at" {...axisProps} interval="preserveStartEnd" />
        <YAxis {...axisProps} domain={[0, 100]} width={40} />
        <Tooltip
          content={(p: TooltipContentProps) => (
            <Tip {...p} fmt={(v) => v.toFixed(1)} />
          )}
        />
        <Line
          type="monotone"
          dataKey="value"
          name="Score"
          stroke={TEAL}
          strokeWidth={2}
          dot={{ r: 3, fill: TEAL, strokeWidth: 0 }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

/** Half-circle gauge — pure SVG arc, band-colored on the 0-100 value.
 *  Doubles as the p_alive gauge (value = p*100, display = p.toFixed(2)). */
export function CiqDial({
  value,
  label = "CIQ · PARTIAL",
  display,
}: {
  value: number;
  label?: string;
  display?: string;
}) {
  const r = 84;
  const c = Math.PI * r; // half circle
  const filled = (Math.max(0, Math.min(100, value)) / 100) * c;
  const color = bandColor(value);
  return (
    <div className="flex flex-col items-center">
      <svg viewBox="0 0 220 130" className="w-full max-w-70">
        <path
          d={`M 26 114 A ${r} ${r} 0 0 1 194 114`}
          fill="none"
          stroke={GRID}
          strokeWidth={12}
          strokeLinecap="round"
        />
        <path
          d={`M 26 114 A ${r} ${r} 0 0 1 194 114`}
          fill="none"
          stroke={color}
          strokeWidth={12}
          strokeLinecap="round"
          strokeDasharray={`${filled} ${c}`}
        />
        <text
          x="110"
          y="98"
          textAnchor="middle"
          fill="#faf7f0"
          fontSize="44"
          fontFamily="var(--font-plex)"
        >
          {display ?? value.toFixed(1)}
        </text>
        <text
          x="110"
          y="122"
          textAnchor="middle"
          fill="#9aa3b5"
          fontSize="11"
          letterSpacing="2"
          fontFamily="var(--font-inter)"
        >
          {label}
        </text>
      </svg>
    </div>
  );
}

/** 12-month LTV decile boundaries (D1..D10), teal bars. */
export function DecileBars({ deciles }: { deciles: number[] }) {
  const rows = deciles.map((v, i) => ({ decile: `D${i + 1}`, LTV: v }));
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 8 }} barCategoryGap="25%">
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="decile" {...axisProps} />
        <YAxis {...axisProps} tickFormatter={formatINRCompact} width={64} />
        <Tooltip
          cursor={{ fill: "rgba(250,247,240,0.04)" }}
          content={(p: TooltipContentProps) => (
            <Tip {...p} fmt={formatINRCompact} />
          )}
        />
        <Bar dataKey="LTV" fill={TEAL} radius={[3, 3, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Experiment cadence sparkline: starts per month, marigold bars. */
export function CadenceBars({
  data,
}: {
  data: { month: string; count: number }[];
}) {
  const rows = data.map((d) => ({ month: formatMonth(d.month), Started: d.count }));
  return (
    <ResponsiveContainer width="100%" height={110}>
      <BarChart data={rows} margin={{ top: 4, right: 8, bottom: 0, left: 8 }} barCategoryGap="35%">
        <XAxis dataKey="month" {...axisProps} interval="preserveStartEnd" />
        <YAxis {...axisProps} allowDecimals={false} width={24} />
        <Tooltip
          cursor={{ fill: "rgba(250,247,240,0.04)" }}
          content={(p: TooltipContentProps) => (
            <Tip {...p} fmt={(v) => String(v)} />
          )}
        />
        <Bar dataKey="Started" fill={MARIGOLD} radius={[2, 2, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
