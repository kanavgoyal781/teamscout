import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeAll, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
}));

vi.mock("../../lib/api", () => ({
  API_BASE: "http://localhost:8000",
  fetchHealth: async () => ({ ok: true, checks: {} }),
}));

vi.mock("../ui/ThemeToggle", () => ({
  default: () => null,
}));

vi.mock("../tour/DemoTour", () => ({
  default: () => null,
}));

vi.mock("sonner", () => ({
  toast: { message: vi.fn() },
}));

import Sidebar from "./Sidebar";

beforeAll(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }),
  });
});

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("Beta roadmap modals", () => {
  it("opens Outreach modal (portaled to body) and closes on Escape", async () => {
    wrap(<Sidebar />);
    fireEvent.click(screen.getByTestId("beta-nav-outreach"));
    const modal = await screen.findByTestId("beta-modal-outreach");
    expect(modal).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    // Portaled out of the sticky sidebar so fixed stacking is viewport-relative
    expect(modal.parentElement).toBe(document.body);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByTestId("beta-modal-outreach")).not.toBeInTheDocument();
  });

  it("opens Applications Tracker modal", async () => {
    wrap(<Sidebar />);
    fireEvent.click(screen.getByTestId("beta-nav-tracker"));
    expect(await screen.findByTestId("beta-modal-tracker")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Applications Tracker/i })).toBeInTheDocument();
  });

  it("closes on backdrop click but keeps open when dialog content is clicked", async () => {
    wrap(<Sidebar />);
    fireEvent.click(screen.getByTestId("beta-nav-outreach"));
    const backdrop = await screen.findByTestId("beta-modal-outreach");
    // stopPropagation on dialog: content click must not close
    fireEvent.click(screen.getByRole("dialog"));
    expect(screen.getByTestId("beta-modal-outreach")).toBeInTheDocument();
    fireEvent.click(backdrop);
    expect(screen.queryByTestId("beta-modal-outreach")).not.toBeInTheDocument();
  });

  it("restores focus to the beta nav trigger after close", async () => {
    wrap(<Sidebar />);
    const trigger = screen.getByTestId("beta-nav-outreach");
    trigger.focus();
    fireEvent.click(trigger);
    await screen.findByTestId("beta-modal-outreach");
    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => {
      expect(screen.queryByTestId("beta-modal-outreach")).not.toBeInTheDocument();
    });
    await waitFor(() => {
      expect(document.activeElement).toBe(trigger);
    });
  });

  it("traps Tab within the beta dialog", async () => {
    wrap(<Sidebar />);
    fireEvent.click(screen.getByTestId("beta-nav-outreach"));
    await screen.findByTestId("beta-modal-outreach");
    const close = screen.getByRole("button", { name: "Close roadmap dialog" });
    const notify = screen.getByTestId("beta-notify-outreach");
    // Close is first focusable (header), Notify me then Close (footer) — last is footer Close
    const footerClose = screen.getByRole("button", { name: "Close" });
    close.focus();
    fireEvent.keyDown(window, { key: "Tab", shiftKey: true });
    await waitFor(() => {
      expect(document.activeElement).toBe(footerClose);
    });
    fireEvent.keyDown(window, { key: "Tab" });
    await waitFor(() => {
      expect(document.activeElement).toBe(close);
    });
    // Sanity: Notify me is a middle focusable
    notify.focus();
    expect(document.activeElement).toBe(notify);
  });
});
