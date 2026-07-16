"use client";

import type { FieldConfidence } from "../../lib/types";

export default function AutoDetectedChip({
  confidence,
}: {
  confidence?: FieldConfidence;
}) {
  const amber = confidence === "low";
  return (
    <span
      className={`auto-chip${amber ? " auto-chip-low" : ""}`}
      title={confidence ? `Confidence: ${confidence}` : "Auto-detected from job text"}
    >
      auto-detected
    </span>
  );
}
