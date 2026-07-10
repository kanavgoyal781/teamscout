import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("framer-motion", async () => {
  const actual = await vi.importActual<typeof import("framer-motion")>("framer-motion");
  return { ...actual, useReducedMotion: () => true };
});

import DemoTour, { TOUR_STEPS } from "./DemoTour";

function mountAnchors(includeTargets = true) {
  document.body.innerHTML = includeTargets
    ? `
      <button data-tour="nav-feature-1" data-testid="demo-tour-start">Demo tour</button>
      <div data-tour="resume-wizard"></div>
      <div data-tour="wizard-stepper"></div>
      <div data-tour="nav-about"></div>
      <div data-tour="credit-confirm"></div>
    `
    : `<button data-testid="demo-tour-start">Demo tour</button>`;
}

describe("DemoTour", () => {
  beforeEach(() => {
    mountAnchors(true);
    Element.prototype.scrollIntoView = vi.fn();
    // Flush rAF immediately so layout focus + measure timeouts are testable
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
      cb(0);
      return 1;
    });
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
  });

  it("moves focus to Next on open without manual focus()", async () => {
    const focusSpy = vi.spyOn(HTMLElement.prototype, "focus");
    render(<DemoTour open onClose={vi.fn()} />);
    const next = await screen.findByTestId("demo-tour-next");
    await waitFor(() => {
      const instances = focusSpy.mock.instances as unknown as HTMLElement[];
      const focusedNext = instances.some((el) => el === next);
      expect(focusedNext || document.activeElement === next).toBe(true);
    });
    focusSpy.mockRestore();
  });

  it("has dialog a11y wiring (labelledby + describedby + modal)", async () => {
    render(<DemoTour open onClose={vi.fn()} />);
    const dialog = await screen.findByTestId("demo-tour");
    expect(dialog).toHaveAttribute("role", "dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    const labelledBy = dialog.getAttribute("aria-labelledby");
    const describedBy = dialog.getAttribute("aria-describedby");
    expect(labelledBy).toBeTruthy();
    expect(describedBy).toBeTruthy();
    expect(document.getElementById(labelledBy!)).toHaveTextContent(/Feature 1/i);
    expect(document.getElementById(describedBy!)).toBeTruthy();
  });

  it("disables Back on step 0; ArrowRight advances; ArrowLeft goes back", async () => {
    render(<DemoTour open onClose={vi.fn()} />);
    expect(await screen.findByTestId("demo-tour-prev")).toBeDisabled();
    expect(screen.getByTestId("demo-tour-step-label")).toHaveTextContent("Step 1 / 5");

    fireEvent.keyDown(window, { key: "ArrowRight" });
    await waitFor(() => {
      expect(screen.getByTestId("demo-tour-step-label")).toHaveTextContent("Step 2 / 5");
    });
    expect(screen.getByTestId("demo-tour-prev")).not.toBeDisabled();

    fireEvent.keyDown(window, { key: "ArrowLeft" });
    await waitFor(() => {
      expect(screen.getByTestId("demo-tour-step-label")).toHaveTextContent("Step 1 / 5");
    });

    fireEvent.click(screen.getByTestId("demo-tour-next"));
    await waitFor(() => {
      expect(screen.getByTestId("demo-tour-step-label")).toHaveTextContent("Step 2 / 5");
    });
    fireEvent.click(screen.getByTestId("demo-tour-prev"));
    await waitFor(() => {
      expect(screen.getByTestId("demo-tour-step-label")).toHaveTextContent("Step 1 / 5");
    });
  });

  it("Close button calls onClose", async () => {
    const onClose = vi.fn();
    render(<DemoTour open onClose={onClose} />);
    fireEvent.click(await screen.findByTestId("demo-tour-close"));
    expect(onClose).toHaveBeenCalled();
  });

  it("last step shows Finish CTA and closing finishes without credit actions", async () => {
    const onClose = vi.fn();
    render(<DemoTour open onClose={onClose} />);
    await screen.findByTestId("demo-tour-next");
    for (let i = 0; i < TOUR_STEPS.length - 1; i++) {
      fireEvent.click(screen.getByTestId("demo-tour-next"));
    }
    expect(screen.getByTestId("demo-tour-next")).toHaveTextContent(/Finish \(no credit spend\)/i);
    expect(screen.getByTestId("demo-tour-step-label")).toHaveTextContent(
      `Step ${TOUR_STEPS.length} / ${TOUR_STEPS.length}`,
    );
    expect(screen.getByTestId("demo-tour-card")).toHaveTextContent(/Stop before credit spend/i);
    fireEvent.click(screen.getByTestId("demo-tour-next"));
    expect(onClose).toHaveBeenCalled();
  });

  it("shows missing-target copy when anchors are absent", async () => {
    mountAnchors(false);
    render(<DemoTour open onClose={vi.fn()} />);
    expect(await screen.findByTestId("demo-tour-missing", {}, { timeout: 1000 })).toBeInTheDocument();
    expect(screen.getByTestId("demo-tour-missing")).toHaveTextContent(/page stays locked/i);
  });

  it("traps Tab within the tour card", async () => {
    render(<DemoTour open onClose={vi.fn()} />);
    const next = await screen.findByTestId("demo-tour-next");
    const close = screen.getByTestId("demo-tour-close");
    next.focus();
    fireEvent.keyDown(window, { key: "Tab" });
    await waitFor(() => {
      expect(document.activeElement).toBe(close);
    });
    fireEvent.keyDown(window, { key: "Tab", shiftKey: true });
    await waitFor(() => {
      expect(document.activeElement).toBe(next);
    });
  });

  it("exposes TOUR_STEPS length for e2e sync", () => {
    expect(TOUR_STEPS.length).toBe(5);
    expect(TOUR_STEPS[TOUR_STEPS.length - 1]?.id).toBe("credit-gate");
  });
});
