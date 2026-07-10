"use client";

import { useEffect, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";

import { formatScore } from "../../lib/format";
import { easeOutSlow } from "../../lib/motion";

type ScoreRingProps = {
  score: number;
  size?: number;
  label?: string;
};

export default function ScoreRing({ score, size = 56, label = "Match" }: ScoreRingProps) {
  const reduced = useReducedMotion();
  const clamped = Math.min(100, Math.max(0, Number.isFinite(score) ? score : 0));
  const stroke = 5;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const offset = c - (clamped / 100) * c;
  const [shown, setShown] = useState(reduced ? clamped : 0);

  useEffect(() => {
    if (reduced) {
      setShown(clamped);
      return;
    }
    let raf = 0;
    const from = 0;
    const start = performance.now();
    const dur = 650;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / dur);
      const e = 1 - Math.pow(1 - t, 3);
      setShown(from + (clamped - from) * e);
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [clamped, reduced]);

  return (
    <div className="score-ring-wrap" aria-label={`${label} score ${formatScore(clamped)}`}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="var(--bg-muted)"
          strokeWidth={stroke}
        />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="var(--accent)"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          initial={reduced ? { strokeDashoffset: offset } : { strokeDashoffset: c }}
          animate={{ strokeDashoffset: offset }}
          transition={reduced ? { duration: 0 } : easeOutSlow}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
        <text
          x="50%"
          y="50%"
          dominantBaseline="central"
          textAnchor="middle"
          className="font-num"
          fill="var(--text)"
          fontSize={size * 0.28}
          fontFamily="var(--font-mono)"
          fontWeight={600}
        >
          {formatScore(shown)}
        </text>
      </svg>
      <span className="score-ring-label">{label}</span>
    </div>
  );
}
