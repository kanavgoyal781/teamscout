"use client";

import type { Transition, Variants } from "framer-motion";

/** Default ease-out in the 150–250ms band. */
export const easeOut: Transition = {
  duration: 0.2,
  ease: [0.16, 1, 0.3, 1],
};

export const easeOutSlow: Transition = {
  duration: 0.25,
  ease: [0.16, 1, 0.3, 1],
};

export const staggerContainer: Variants = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.06, delayChildren: 0.04 },
  },
};

export const staggerItem: Variants = {
  hidden: { opacity: 0, y: 10 },
  show: { opacity: 1, y: 0, transition: easeOut },
};

export const cardHover = {
  y: -2,
  transition: easeOut,
};

export function motionSafe(reduced: boolean | null): boolean {
  return Boolean(reduced);
}

/** True when animation entrance should be skipped (a11y or automated browsers). */
export function shouldSkipEntrance(reduced: boolean | null): boolean {
  if (reduced) return true;
  if (typeof navigator !== "undefined" && (navigator as Navigator & { webdriver?: boolean }).webdriver) {
    return true;
  }
  return false;
}
