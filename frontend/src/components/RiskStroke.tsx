/** Risk shown as one wobbly pen stroke: its length is the probability, its
 *  colour is the tier. The stroke is seeded so a record always draws the same
 *  line. */

import type { Tier } from "../lib/types";

const TIER_INK: Record<Tier, string> = {
  low: "var(--verdigris)",
  medium: "var(--haldi)",
  high: "var(--stamp-red)",
};

function hash(seed: string): number {
  let h = 2166136261;
  for (let i = 0; i < seed.length; i += 1) {
    h = Math.imul(h ^ seed.charCodeAt(i), 16777619);
  }
  return h >>> 0;
}

interface RiskStrokeProps {
  probability: number;
  tier: Tier;
  seed: string;
  width?: number;
  label?: string;
}

export default function RiskStroke({ probability, tier, seed, width = 96, label }: RiskStrokeProps) {
  const end = 2 + width * Math.max(0, Math.min(1, probability));
  const wobble = (i: number) => ((hash(seed + i) % 7) - 3) * 0.9;
  const mid1 = 2 + (end - 2) * 0.34;
  const mid2 = 2 + (end - 2) * 0.68;
  const d = `M 2 9 Q ${mid1} ${9 + wobble(1)} ${mid2} ${9 + wobble(2)} T ${end} ${9 + wobble(3)}`;

  return (
    <span className="stamp-cell">
      <svg width={width + 4} height="18" viewBox={`0 0 ${width + 4} 18`} aria-hidden="true">
        <path d={d} fill="none" stroke={TIER_INK[tier]} strokeWidth="5" strokeLinecap="round" opacity="0.85" />
      </svg>
      {label ? <span className="num">{label}</span> : null}
    </span>
  );
}
