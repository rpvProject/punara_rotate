import { BodyText, CTAButton, Eyebrow, H2, Section } from "@/components/ui";
import { config } from "@/lib/config";

/* Copy verbatim from site/COPY.md §7. The four vignettes are stylized
   JSX/CSS depictions of Lens modules (same visual language as the hero
   mockup: Nightfall panels, mono numerals, teal = good / ember = leak).
   They are decorative (aria-hidden); the accessible copy is the module
   name + caption in each figcaption.
   TODO(copy): micro-labels inside the vignettes (month abbreviations,
   "CIQ", score names, "LOW/MEDIUM/HIGH" risk bands) are not in COPY.md —
   they are illustrative UI fragments, not page copy. Flagged to the
   copy owner. */

const listedModules: Array<{ name: string; caption: string }> = [
  {
    name: "Customer Analytics",
    caption:
      "AOV, frequency, repurchase latency, and margin by cohort, channel, and first product.",
  },
  {
    name: "Revenue & Leak Map",
    caption:
      "Every preventable leak — churn, RTO/COD, failed payments, discount abuse — sized in rupees and ranked.",
  },
  {
    name: "Customer Timeline",
    caption:
      "Every order, message, delivery event, and support ticket for one customer, on one axis.",
  },
  {
    name: "Journey Builder",
    caption:
      "Design the journey in Lens; compile it to Klaviyo and Interakt. The thinking here, the sending there.",
  },
  {
    name: "Retention Attribution",
    caption:
      "Flow-attributed revenue measured with holdouts: what your automations actually earned, not what they claim.",
  },
  {
    name: "AI Executive Reports",
    caption:
      "Veda writes the monthly summary; every number in it traces back to the query that produced it.",
  },
];

function Vignette({
  name,
  caption,
  className,
  children,
}: {
  name: string;
  caption: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <figure className={`flex flex-col ${className ?? ""}`}>
      <div
        aria-hidden="true"
        className="flex-1 overflow-hidden rounded-lg border border-panel2 bg-nightfall p-4"
      >
        {children}
      </div>
      <figcaption className="mt-3">
        <span className="block font-display text-base tracking-tight text-ink">
          {name}
        </span>
        <span className="mt-1 block text-sm leading-relaxed text-muted">
          {caption}
        </span>
      </figcaption>
    </figure>
  );
}

const execScores: Array<[string, number]> = [
  ["GRAVITY", 54],
  ["FLOW", 61],
  ["SIGNAL", 72],
  ["VITALS", 66],
  ["AUTOPILOT", 43],
  ["VELOCITY", 48],
];

function ExecMock() {
  return (
    <div className="flex h-full flex-col font-mono">
      <div className="text-[10px] tracking-[0.2em] text-bone/40">
        PUNARA CIQ
      </div>
      <div className="mt-2 flex items-baseline gap-2">
        <span className="num text-4xl text-bone">58</span>
        <span className="num text-sm text-teal">+4</span>
      </div>
      <div className="mt-4 flex flex-1 flex-col justify-between gap-2">
        {execScores.map(([label, v]) => (
          <div key={label} className="flex items-center gap-2">
            <span className="w-20 shrink-0 text-[9px] tracking-[0.15em] text-bone/40">
              {label}
            </span>
            <span className="h-1 flex-1 rounded-full bg-bone/10">
              <span
                className="block h-full rounded-full bg-teal/70"
                style={{ width: `${v}%` }}
              />
            </span>
            <span className="num text-[10px] text-bone/70">{v}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

const months = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN"];

function CohortMock() {
  return (
    <div className="font-mono">
      <div className="text-[10px] tracking-[0.2em] text-bone/40">
        RETENTION BY ACQUISITION MONTH
      </div>
      <div className="mt-3 space-y-1">
        {months.map((m, r) => (
          <div key={m} className="flex items-center gap-1">
            <span className="w-8 shrink-0 text-[9px] text-bone/40">{m}</span>
            {Array.from({ length: 9 - r }, (_, c) => {
              const opacity = Math.max(
                0.07,
                0.85 * Math.pow(0.76, c) + (((r * 7 + c * 3) % 5) - 2) * 0.02,
              );
              return (
                <span
                  key={c}
                  className="h-4 flex-1 rounded-[2px] bg-teal"
                  style={{ opacity }}
                />
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

const bands: Array<{
  label: string;
  width: number;
  count: string;
  color: string;
}> = [
  { label: "LOW", width: 78, count: "9,412", color: "bg-teal/70" },
  { label: "MEDIUM", width: 30, count: "3,048", color: "bg-bone/30" },
  { label: "HIGH", width: 12, count: "1,384", color: "bg-ember/80" },
];

function ChurnMock() {
  return (
    <div className="font-mono">
      <div className="text-[10px] tracking-[0.2em] text-bone/40">
        CHURN RISK · 12-MO LTV
      </div>
      <div className="mt-3 space-y-3">
        {bands.map((b) => (
          <div key={b.label}>
            <div className="flex justify-between text-[9px] text-bone/40">
              <span>{b.label}</span>
              <span className="num text-bone/70">{b.count}</span>
            </div>
            <div className="mt-1 h-2 rounded-full bg-bone/10">
              <span
                className={`block h-full rounded-full ${b.color}`}
                style={{ width: `${b.width}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

const rfmCounts = [
  ["2,140", "1,462", "918", "541"],
  ["1,733", "1,205", "760", "402"],
  ["1,381", "947", "533", "296"],
  ["1,048", "702", "384", "163"],
];

function RfmMock() {
  return (
    <div className="font-mono">
      <div className="text-[10px] tracking-[0.2em] text-bone/40">
        RFM · 16 CELLS
      </div>
      <div className="mt-3 grid grid-cols-4 gap-1">
        {rfmCounts.map((row, r) =>
          row.map((count, c) => {
            const atRisk = r === 3 && c === 0;
            return (
              <span
                key={`${r}-${c}`}
                className={`flex h-8 items-center justify-center rounded-[2px] text-[9px] ${
                  atRisk ? "bg-ember/60 text-bone" : "bg-teal text-bone"
                }`}
                style={
                  atRisk
                    ? undefined
                    : { opacity: Math.max(0.12, 0.85 - (r + c) * 0.11) }
                }
              >
                <span className="num">{count}</span>
              </span>
            );
          }),
        )}
      </div>
    </div>
  );
}

export function Platform() {
  return (
    <Section id="platform">
      <Eyebrow>PUNARA LENS</Eyebrow>
      <H2 className="mt-4">The instrument our consultants answer to.</H2>
      <BodyText className="mt-4">
        Every retainer runs on Punara Lens. It reads the stack you already have
        — Shopify, Razorpay, Shiprocket, Klaviyo, Interakt — and adds zero
        sending infrastructure: we decide who gets what and why; your existing
        pipes carry the message.
      </BodyText>

      <div className="mt-12 grid gap-x-6 gap-y-10 md:grid-cols-3">
        <Vignette
          name="Executive Dashboard"
          caption="CIQ and the ten scores, with monthly movement. The board slide, live."
          className="md:row-span-2"
        >
          <ExecMock />
        </Vignette>
        <Vignette
          name="Cohort Retention"
          caption="Decay curves by acquisition month. See which cohort is quietly dying, and when it started."
          className="md:col-span-2"
        >
          <CohortMock />
        </Vignette>
        <Vignette
          name="Predictions"
          caption="Per-customer churn risk and 12-month LTV (BG/NBD + XGBoost), with model lift stated against a naive baseline."
        >
          <ChurnMock />
        </Vignette>
        <Vignette
          name="Segmentation & RFM"
          caption="Behavioural and predictive segments with sync rules into your messaging stack."
        >
          <RfmMock />
        </Vignette>
      </div>

      <dl className="mt-12 grid gap-x-10 border-t border-line md:grid-cols-2">
        {listedModules.map((m) => (
          <div key={m.name} className="border-b border-line py-4">
            <dt className="text-sm font-medium text-ink">{m.name}</dt>
            <dd className="mt-1 text-sm leading-relaxed text-muted">
              {m.caption}
            </dd>
          </div>
        ))}
      </dl>

      <BodyText className="mt-10">
        Every screenshot on this page is the working product running on
        realistic seed data — not concept art. From week one of a Decode, these
        screens show your data.
      </BodyText>

      <CTAButton
        variant="secondary"
        href={config.platformUrl}
        className="mt-6"
      >
        Explore the platform
      </CTAButton>
    </Section>
  );
}
