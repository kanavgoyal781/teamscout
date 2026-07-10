import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const reducedMotion = { current: true };

vi.mock("framer-motion", async () => {
  const actual = await vi.importActual<typeof import("framer-motion")>("framer-motion");
  return { ...actual, useReducedMotion: () => reducedMotion.current };
});

import CountUp from "./CountUp";

describe("CountUp", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    reducedMotion.current = true;
  });

  it("snaps to final value when reduced motion", () => {
    reducedMotion.current = true;
    render(<CountUp value={42} />);
    expect(screen.getByTestId("count-up")).toHaveTextContent("42");
  });

  it("formats decimals", () => {
    reducedMotion.current = true;
    render(<CountUp value={1.2345} decimals={4} />);
    expect(screen.getByTestId("count-up")).toHaveTextContent("1.2345");
  });

  it("treats non-finite as 0", () => {
    reducedMotion.current = true;
    render(<CountUp value={Number.NaN} />);
    expect(screen.getByTestId("count-up")).toHaveTextContent("0");
  });

  it("animates toward final value when motion is allowed", async () => {
    reducedMotion.current = false;
    let now = 0;
    vi.spyOn(performance, "now").mockImplementation(() => now);
    const callbacks: FrameRequestCallback[] = [];
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
      callbacks.push(cb);
      return callbacks.length;
    });
    vi.stubGlobal("cancelAnimationFrame", vi.fn());

    render(<CountUp value={100} durationMs={100} />);
    // initial frame before first RAF tick may be 0
    expect(screen.getByTestId("count-up").textContent).toMatch(/0|100/);

    // Drive animation to completion
    now = 50;
    callbacks.shift()?.(now);
    now = 100;
    // process remaining queued frames (ease may queue more)
    let guard = 0;
    while (callbacks.length > 0 && guard < 20) {
      const cb = callbacks.shift()!;
      now = Math.min(now + 50, 200);
      cb(now);
      guard += 1;
    }

    await waitFor(() => {
      expect(screen.getByTestId("count-up")).toHaveTextContent("100");
    });
  });
});
