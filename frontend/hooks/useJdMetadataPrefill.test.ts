import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";

import { shouldDiscardExtract, useJdMetadataPrefill } from "./useJdMetadataPrefill";

const extractJobMetadata = vi.fn();

vi.mock("../lib/api", () => ({
  extractJobMetadata: (...args: unknown[]) => extractJobMetadata(...args),
}));

function meta(partial: Record<string, unknown> = {}) {
  return {
    metadata: {
      title: "Senior Data Scientist",
      company: "Acme Analytics",
      location: "Remote",
      remote_mode: "remote",
      salary_min: null,
      salary_max: null,
      salary_currency: null,
      seniority: "senior",
      department: null,
      confidence: { title: "high", company: "low", location: "medium" },
      ...partial,
    },
    cache_hit: false,
    content_hash: "abc",
  };
}

describe("shouldDiscardExtract", () => {
  it("discards when seq advanced (short-text or newer paste)", () => {
    expect(shouldDiscardExtract(1, 2)).toBe(true);
    expect(shouldDiscardExtract(3, 3)).toBe(false);
  });
});

describe("useJdMetadataPrefill", () => {
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
      ({ desc }) => useJdMetadataPrefill(desc, { setTitle, setCompany, setLocation }),
      { initialProps: { desc: long } },
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(800);
    });
    expect(extractJobMetadata).toHaveBeenCalledTimes(1);

    await act(async () => {
      rerender({ desc: "short" });
    });
    expect(result.current.detecting).toBe(false);

    await act(async () => {
      resolveExtract(meta({ title: "ShouldNotApply", company: "GhostCo", location: "Nowhere" }));
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(setTitle).not.toHaveBeenCalledWith("ShouldNotApply");
    expect(setCompany).not.toHaveBeenCalledWith("GhostCo");
    expect(setLocation).not.toHaveBeenCalledWith("Nowhere");
  });

  it("prefills title/company/location after debounce when JD is long", async () => {
    extractJobMetadata.mockResolvedValue(meta());
    const setTitle = vi.fn();
    const setCompany = vi.fn();
    const setLocation = vi.fn();
    const long = "We are hiring a Senior Data Scientist at Acme. ".repeat(10);

    const { result } = renderHook(() =>
      useJdMetadataPrefill(long, { setTitle, setCompany, setLocation }),
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(800);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(extractJobMetadata).toHaveBeenCalled();
    expect(setTitle).toHaveBeenCalledWith("Senior Data Scientist");
    expect(setCompany).toHaveBeenCalledWith("Acme Analytics");
    expect(setLocation).toHaveBeenCalledWith("Remote");
    expect(result.current.autoFields.title).toBe(true);
    expect(result.current.autoFields.company).toBe(true);
    expect(result.current.confidence("company")).toBe("low");
  });

  it("dirty field is never overwritten by a late re-extract", async () => {
    extractJobMetadata
      .mockResolvedValueOnce(meta({ title: "Role A", company: "Co A", location: "SF" }))
      .mockResolvedValue(meta({ title: "Role B", company: "ShouldNotOverwrite", location: "NYC" }));

    const setTitle = vi.fn();
    const setCompany = vi.fn();
    const setLocation = vi.fn();
    const long1 = "A".repeat(220);
    const long2 = "B".repeat(220);

    const { result, rerender } = renderHook(
      ({ desc }) => useJdMetadataPrefill(desc, { setTitle, setCompany, setLocation }),
      { initialProps: { desc: long1 } },
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(800);
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(setCompany).toHaveBeenCalledWith("Co A");

    // User edits company → dirty
    await act(async () => {
      result.current.setCompany("My Manual Co");
    });
    expect(result.current.autoFields.company).toBeUndefined();

    setCompany.mockClear();
    setTitle.mockClear();
    setLocation.mockClear();
    await act(async () => {
      rerender({ desc: long2 });
      result.current.onDescriptionPaste(long2);
      await Promise.resolve();
      await Promise.resolve();
    });

    // Dirty company never overwritten; non-dirty title/location may update
    expect(setCompany).not.toHaveBeenCalledWith("ShouldNotOverwrite");
    expect(setTitle).toHaveBeenCalledWith("Role B");
    expect(setLocation).toHaveBeenCalledWith("NYC");
  });

  it("failure leaves form manual without applying values", async () => {
    extractJobMetadata.mockRejectedValue(new Error("timeout"));
    const setTitle = vi.fn();
    const setCompany = vi.fn();
    const setLocation = vi.fn();
    const long = "y".repeat(250);

    const { result } = renderHook(() =>
      useJdMetadataPrefill(long, { setTitle, setCompany, setLocation }),
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(800);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(result.current.detecting).toBe(false);
    expect(setTitle).not.toHaveBeenCalled();
    expect(Object.keys(result.current.autoFields)).toHaveLength(0);
  });

  it("onDescriptionPaste fires extract immediately for long text", async () => {
    extractJobMetadata.mockResolvedValue(meta());
    const setTitle = vi.fn();
    const setCompany = vi.fn();
    const setLocation = vi.fn();
    const long = "z".repeat(250);

    const { result } = renderHook(() =>
      useJdMetadataPrefill("", { setTitle, setCompany, setLocation }),
    );

    await act(async () => {
      result.current.onDescriptionPaste(long);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(extractJobMetadata).toHaveBeenCalled();
    expect(setTitle).toHaveBeenCalledWith("Senior Data Scientist");
  });
});
