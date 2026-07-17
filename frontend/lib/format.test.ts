import { describe, expect, it } from "vitest";
import {
  formatCostUsd,
  formatLatencyMs,
  formatScore,
  middleTruncate,
} from "./format";

describe("M26 format craft", () => {
  it("formatScore is integer", () => {
    expect(formatScore(87.4)).toBe("87");
    expect(formatScore(91.9)).toBe("92");
  });

  it("formatLatencyMs has no decimals", () => {
    expect(formatLatencyMs(320.7)).toBe("321");
    expect(formatLatencyMs(null)).toBe("—");
  });

  it("formatCostUsd is 2dp", () => {
    expect(formatCostUsd(1.2)).toBe("1.20");
    expect(formatCostUsd(0.0006)).toBe("0.00");
  });

  it("middleTruncate keeps ends for pathological names", () => {
    const a = "Kanav_Data_Science_______.pdf";
    const b = "Kanav Goyal_AI (2) (3).pdf";
    const ta = middleTruncate(a, 28);
    const tb = middleTruncate(b, 22);
    expect(ta.length).toBeLessThanOrEqual(29);
    expect(ta.startsWith("Kanav")).toBe(true);
    expect(ta.endsWith(".pdf") || ta.includes("pdf")).toBe(true);
    expect(ta).toContain("…");
    expect(tb).toContain("…");
    expect(tb.startsWith("Kanav")).toBe(true);
    expect(middleTruncate("short.pdf")).toBe("short.pdf");
    // at default max 28, (2)(3) name is short enough to pass through
    expect(middleTruncate(b, 40)).toBe(b);
  });
});
