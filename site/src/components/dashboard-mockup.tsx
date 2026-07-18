/* Stylized miniature of the real Lens overview (lens/web/src/app/page.tsx):
   CIQ half-dial, four score tiles with band tracks, cohort decay heatmap,
   leak-map bars. Pure JSX/SVG/CSS — no images, no chart libs. Figures are
   illustrative seed data (aria-hidden); the hero figcaption carries the
   accessible description. Dark-context only (rendered inside the hero). */

const DIAL_R = 84;
const DIAL_C = Math.PI * DIAL_R;
/* One CIQ across every mockup on the page — 58 (+4), matching the platform
   section's Executive Dashboard vignette. Numerate visitors count. */
const CIQ = 58;

const SCORES = [
  { label: "Gravity", value: "35.8", pct: 35.8, tone: "text-ember", bar: "#E0533D" },
  { label: "Signal", value: "98.5", pct: 98.5, tone: "text-teal", bar: "#0FA284" },
  { label: "Vitals", value: "86.5", pct: 86.5, tone: "text-teal", bar: "#0FA284" },
  { label: "Watertight", value: "39.2", pct: 39.2, tone: "text-ember", bar: "#E0533D" },
];

/* Retention % by month since acquisition — each later cohort decays faster. */
const COHORTS = [
  [100, 46, 34, 27, 22, 19],
  [100, 41, 30, 23, 18, 15],
  [100, 37, 26, 19, 14, 11],
  [100, 33, 22, 15, 11, 8],
];

const LEAKS = [
  { label: "RTO / COD", amount: "₹1.4cr", w: 100 },
  { label: "Discount abuse", amount: "₹97L", w: 66 },
  { label: "Failed payments", amount: "₹38L", w: 26 },
];

export function DashboardMockup() {
  return (
    <div
      aria-hidden="true"
      className="mockup-rise overflow-hidden rounded-xl border border-line bg-panel shadow-[0_32px_80px_-32px_rgba(0,0,0,0.7)]"
    >
      <style>{`
        @keyframes mockup-rise { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: none; } }
        .mockup-rise { animation: mockup-rise 0.7s ease-out both; }
        @media (prefers-reduced-motion: reduce) { .mockup-rise { animation: none; } }
      `}</style>

      {/* chrome */}
      <div className="flex items-center justify-between border-b border-line px-4 py-3 md:px-6">
        <span className="font-display text-sm tracking-tight text-bone">
          Punara Lens
        </span>
        <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted">
          Overview · seed data
        </span>
      </div>

      <div className="p-4 md:p-6">
        {/* dial + score tiles */}
        <div className="grid gap-3 md:grid-cols-[260px_1fr]">
          <div className="flex flex-col items-center justify-center rounded-md border border-line bg-panel2 p-4">
            <span className="self-start font-mono text-[9px] uppercase tracking-[0.18em] text-graphite">
              Customer Intelligence Quotient
            </span>
            <svg viewBox="0 0 220 130" className="mt-2 w-full max-w-[210px]">
              <path
                d={`M 26 114 A ${DIAL_R} ${DIAL_R} 0 0 1 194 114`}
                fill="none"
                stroke="#232B3D"
                strokeWidth={12}
                strokeLinecap="round"
              />
              <path
                d={`M 26 114 A ${DIAL_R} ${DIAL_R} 0 0 1 194 114`}
                fill="none"
                stroke="#F2A413"
                strokeWidth={12}
                strokeLinecap="round"
                strokeDasharray={`${(CIQ / 100) * DIAL_C} ${DIAL_C}`}
              />
              <text
                x="110"
                y="98"
                textAnchor="middle"
                fill="#FAF7F0"
                fontSize="42"
                fontFamily="var(--font-plex)"
              >
                58
              </text>
              <text
                x="140"
                y="96"
                textAnchor="start"
                fill="#0FA284"
                fontSize="14"
                fontFamily="var(--font-plex)"
              >
                +4
              </text>
              <text
                x="110"
                y="122"
                textAnchor="middle"
                fill="#9AA3B5"
                fontSize="10"
                letterSpacing="2"
                fontFamily="var(--font-plex)"
              >
                CIQ · 0–100
              </text>
            </svg>
            <span className="num mt-3 text-center text-[9px] uppercase tracking-[0.08em] text-graphite">
              0–40 Leaking · 40–70 Building · 70–100 Compounding
            </span>
          </div>

          <div className="grid grid-cols-2 gap-3">
            {SCORES.map((s) => (
              <div
                key={s.label}
                className="flex flex-col justify-between rounded-md border border-line bg-panel2 p-4"
              >
                <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted">
                  {s.label}
                </span>
                <span className={`num mt-1 text-2xl lg:text-3xl ${s.tone}`}>
                  {s.value}
                </span>
                <span className="mt-3 block h-1 rounded-full bg-[#232B3D]">
                  <span
                    className="block h-1 rounded-full"
                    style={{ width: `${s.pct}%`, background: s.bar }}
                  />
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* cohort heatmap + leak map */}
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <div className="rounded-md border border-line bg-panel2 p-4">
            <span className="font-mono text-[9px] uppercase tracking-[0.18em] text-graphite">
              Cohort retention · months since first order
            </span>
            <div className="mt-3 space-y-1.5">
              {COHORTS.map((row, i) => (
                <div key={i} className="grid grid-cols-6 gap-1.5">
                  {row.map((v, j) => (
                    <span
                      key={j}
                      className="block h-3.5 rounded-[2px] bg-teal"
                      style={{ opacity: Math.max(v / 100, 0.06) }}
                    />
                  ))}
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-md border border-line bg-panel2 p-4">
            <span className="font-mono text-[9px] uppercase tracking-[0.18em] text-graphite">
              Revenue leak map · annualised
            </span>
            <div className="mt-3 space-y-2.5">
              {LEAKS.map((l) => (
                <div key={l.label} className="flex items-center gap-3">
                  <span className="w-28 shrink-0 font-mono text-[10px] uppercase tracking-[0.08em] text-muted">
                    {l.label}
                  </span>
                  <span className="block h-1.5 flex-1 rounded-full bg-[#232B3D]">
                    <span
                      className="block h-1.5 rounded-full bg-ember"
                      style={{ width: `${l.w}%` }}
                    />
                  </span>
                  <span className="num w-14 text-right text-xs text-ember">
                    {l.amount}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
