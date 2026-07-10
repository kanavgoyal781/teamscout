import { describe, expect, it, vi, afterEach } from "vitest";
import { shouldSkipEntrance } from "./motion";

describe("shouldSkipEntrance", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("skips when reduced", () => {
    expect(shouldSkipEntrance(true)).toBe(true);
  });

  it("skips under webdriver", () => {
    vi.stubGlobal("navigator", { webdriver: true });
    expect(shouldSkipEntrance(false)).toBe(true);
  });

  it("does not skip when motion allowed and not webdriver", () => {
    vi.stubGlobal("navigator", { webdriver: false });
    expect(shouldSkipEntrance(false)).toBe(false);
  });
});
