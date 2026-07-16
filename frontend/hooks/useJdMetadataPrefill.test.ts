import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";

import { shouldDiscardExtract, useJdMetadataPrefill } from "./useJdMetadataPrefill";

const extractJobMetadata = vi.fn();

vi.mock("../lib/api", () => ({
  extractJobMetadata: (...args: unknown[]) => extractJobMetadata(...args),
}));

describe("shouldDiscardExtract", () => {
  it("discards when seq advanced (short-text or newer paste)", () => {
    expect(shouldDiscardExtract(1, 2)).toBe(true);
    expect(shouldDiscardExtract(3, 3)).toBe(false);
  });
});

describe("useJdMetadataPrefill short-text race", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    extractJobMetadata.mockReset();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("does not apply late extract after description drops below 200 chars", async () => {
    let resolveExtract: (v: unknown) => void = () => {};
    extractJobMetadata.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveExtract = resolve;
        }),
    );

    const setTitle = vi.fn();
    const setCompany = vi.fn();
    const setLocation = vi.fn();

    const long = "x".repeat(250);
    const { result, rerender } = renderHook(
      ({ desc }) =>
        useJdMetadataPrefill(desc, { setTitle, setCompany, setLocation }),
      { initialProps: { desc: long } },
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(800);
    });
    expect(extractJobMetadata).toHaveBeenCalledTimes(1);

    // User clears / short re-paste before extract resolves
    await act(async () => {
      rerender({ desc: "short" });
    });
    expect(result.current.detecting).toBe(false);

    // Late response arrives
    await act(async () => {
      resolveExtract({
        metadata: {
          title: "ShouldNotApply",
          company: "GhostCo",
          location: "Nowhere",
          remote_mode: null,
          salary_min: null,
          salary_max: null,
          salary_currency: null,
          seniority: null,
          department: null,
          confidence: {},
        },
        cache_hit: false,
        content_hash: "abc",
      });
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(setTitle).not.toHaveBeenCalledWith("ShouldNotApply");
    expect(setCompany).not.toHaveBeenCalledWith("GhostCo");
    expect(setLocation).not.toHaveBeenCalledWith("Nowhere");
  });
});
