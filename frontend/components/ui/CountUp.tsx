"use client";

import { useEffect, useRef, useState } from "react";
import { useReducedMotion } from "framer-motion";

type CountUpProps = {
  value: number;
  durationMs?: number;
  decimals?: number;
  className?: string;
};

/** Animate a number from 0 → value; respects reduced motion. */
export default function CountUp({
  value,
  durationMs = 700,
  decimals = 0,
  className,
}: CountUpProps) {
  const reduced = useReducedMotion();
  const [display, setDisplay] = useState(reduced ? value : 0);
  const fromRef = useRef(0);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    if (reduced || !Number.isFinite(value)) {
      setDisplay(Number.isFinite(value) ? value : 0);
      return;
    }
    const from = fromRef.current;
    const to = value;
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / durationMs);
      // ease-out cubic
      const e = 1 - Math.pow(1 - t, 3);
      const next = from + (to - from) * e;
      setDisplay(next);
      if (t < 1) {
        rafRef.current = requestAnimationFrame(tick);
      } else {
        fromRef.current = to;
      }
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
    };
  }, [value, durationMs, reduced]);

  const formatted =
    decimals > 0 ? display.toFixed(decimals) : Math.round(display).toLocaleString();

  return (
    <span className={className ?? "font-num"} data-testid="count-up">
      {formatted}
    </span>
  );
}
