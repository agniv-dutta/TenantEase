/** Rubber stamp: a double-ruled box with Yatra One lettering and a roughened
 *  edge, as if pressed onto the page. Rotation is seeded so a given record
 *  always lands at the same angle. */

const LABELS = {
  late: { en: "LATE", hi: "", ink: "var(--stamp-red)", text: "var(--stamp-red)" },
  overdue: { en: "OVERDUE", hi: "बाकी", ink: "var(--stamp-red)", text: "var(--stamp-red)" },
  due: { en: "DUE", hi: "देय", ink: "var(--haldi)", text: "var(--indigo)" },
  approved: { en: "APPROVED", hi: "मंज़ूर", ink: "var(--verdigris)", text: "var(--verdigris)" },
} as const;

export type StampKind = keyof typeof LABELS;

function hash(seed: string): number {
  let h = 2166136261;
  for (let i = 0; i < seed.length; i += 1) {
    h = Math.imul(h ^ seed.charCodeAt(i), 16777619);
  }
  return h >>> 0;
}

function ariaLabel(kind: StampKind, detail?: string): string {
  switch (kind) {
    case "late":
      return detail ? `Paid late, ${detail.replace("+", "")}` : "Paid late";
    case "overdue":
      return "Unpaid and overdue";
    case "due":
      return "Due this cycle";
    case "approved":
      return "Reminder approved";
  }
}

interface StampProps {
  kind: StampKind;
  detail?: string;
  seed: string;
  animateIn?: boolean;
  delayMs?: number;
}

export default function Stamp({ kind, detail, seed, animateIn = false, delayMs = 0 }: StampProps) {
  const { en, hi, ink, text } = LABELS[kind];
  const n = hash(seed);
  const rotation = -5 + ((n % 997) / 997) * 10;
  const jitterX = ((n >> 3) % 5) - 2;
  const jitterY = ((n >> 7) % 5) - 2;
  const roughId = `rough-${(n % 100000).toString(36)}`;

  return (
    <span
      className="stamp-cell"
      role="img"
      title={ariaLabel(kind, detail)}
      aria-label={ariaLabel(kind, detail)}
      style={animateIn ? { animation: `stamp-in 120ms ease-out ${delayMs}ms both` } : undefined}
    >
      <svg
        role="img"
        aria-hidden="true"
        width="104"
        height="46"
        viewBox="0 0 104 46"
        style={{
          transform: `rotate(${rotation}deg) translate(${jitterX}px, ${jitterY}px)`,
          mixBlendMode: "multiply",
          overflow: "visible",
        }}
      >
        <defs>
          <filter id={roughId}>
            <feTurbulence type="fractalNoise" baseFrequency="0.04" numOctaves="2" seed={n % 100} result="noise" />
            <feDisplacementMap in="SourceGraphic" in2="noise" scale="2.5" xChannelSelector="R" yChannelSelector="G" result="rough" />
            <feTurbulence type="fractalNoise" baseFrequency="0.7" numOctaves="2" seed={(n >> 5) % 100} result="speckle" />
            <feComposite in="rough" in2="speckle" operator="arithmetic" k1="0" k2="1" k3="0" k4="-0.12" />
          </filter>
        </defs>
        <g filter={`url(#${roughId})`}>
          <rect x="1.5" y="1.5" width="101" height="43" rx="3" fill="none" stroke={ink} strokeWidth="2.6" />
          <rect x="6" y="6" width="92" height="34" rx="3" fill="none" stroke={ink} strokeWidth="1" />
          <text
            x="52"
            y={detail ? 26 : 30}
            textAnchor="middle"
            fill={text}
            style={{ fontFamily: "var(--font-display)", fontSize: 17, letterSpacing: "0.5px" }}
          >
            {en}
          </text>
          {detail && (
            <text
              x="52"
              y="39"
              textAnchor="middle"
              fill={text}
              style={{ fontFamily: "var(--font-body)", fontSize: 10 }}
            >
              {detail}
            </text>
          )}
          {hi && (
            <text x="93" y="17" textAnchor="middle" fill={text} style={{ fontFamily: "var(--font-display)", fontSize: 9, opacity: 0.85 }}>
              {hi}
            </text>
          )}
        </g>
      </svg>
    </span>
  );
}
