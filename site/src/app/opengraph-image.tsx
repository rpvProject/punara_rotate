import { ImageResponse } from "next/og";

/* OG image, generated at build — no external fetches. Canon palette only.
   Font note: Fraunces cannot be embedded — next/font emits woff2 (satori
   needs ttf/otf/woff), no local Fraunces file exists, and runtime network
   fetches are off-limits — so this renders in ImageResponse's bundled
   default font, per the agreed fallback. The dial is decorative: it shows
   no numeric value, so it claims nothing. */

// Required by `output: export` in Next 16 — render the PNG once at build time.
export const dynamic = "force-static";

export const alt =
  "Punara — Your first order is a cost. Your second order is a business.";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const nightfall = "#101623";
const bone = "#FAF7F0";
const marigold = "#F2A413";
const teal = "#0FA284";
const line = "#232B3D";
const muted = "#9AA3B5";

const R = 120;
const CIRC = 2 * Math.PI * R;

export default function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "row",
          alignItems: "center",
          justifyContent: "space-between",
          background: nightfall,
          color: bone,
          padding: "64px 72px",
        }}
      >
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            maxWidth: 760,
            height: "100%",
            justifyContent: "space-between",
          }}
        >
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 28,
            }}
          >
            <div
              style={{
                fontSize: 20,
                letterSpacing: 5,
                color: muted,
              }}
            >
              RETENTION INTELLIGENCE · PUNARA ADVISORY × PUNARA LENS
            </div>
            <div
              style={{
                fontSize: 62,
                lineHeight: 1.15,
                letterSpacing: -1,
              }}
            >
              Your first order is a cost. Your second order is a business.
            </div>
          </div>
          <div
            style={{
              fontSize: 34,
              letterSpacing: 8,
              color: marigold,
            }}
          >
            PUNARA
          </div>
        </div>

        {/* CIQ dial motif — decorative arc, no value claimed */}
        <div
          style={{
            display: "flex",
            position: "relative",
            width: 300,
            height: 300,
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <svg width="300" height="300" viewBox="0 0 300 300">
            <circle
              cx="150"
              cy="150"
              r={R}
              stroke={line}
              strokeWidth="14"
              fill="none"
            />
            <circle
              cx="150"
              cy="150"
              r={R}
              stroke={teal}
              strokeWidth="14"
              fill="none"
              strokeLinecap="round"
              strokeDasharray={`${CIRC * 0.66} ${CIRC}`}
              transform="rotate(-90 150 150)"
            />
            <circle cx="150" cy="30" r="9" fill={marigold} />
          </svg>
          <div
            style={{
              position: "absolute",
              display: "flex",
              fontSize: 44,
              letterSpacing: 6,
              color: bone,
            }}
          >
            CIQ
          </div>
        </div>
      </div>
    ),
    size,
  );
}
