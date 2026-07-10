import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeAll, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
}));

vi.mock("../lib/api", () => ({
  API_BASE: "http://localhost:8000",
  fetchHealth: async () => ({ ok: true, checks: {} }),
}));

vi.mock("./ui/ThemeToggle", () => ({
  default: () => null,
}));

vi.mock("./tour/DemoTour", () => ({
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
  it("opens Outreach modal and closes on Escape", () => {
    wrap(<Sidebar />);
    fireEvent.click(screen.getByTestId("beta-nav-outreach"));
    expect(screen.getByTestId("beta-modal-outreach")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByTestId("beta-modal-outreach")).not.toBeInTheDocument();
  });

  it("opens Applications Tracker modal", () => {
    wrap(<Sidebar />);
    fireEvent.click(screen.getByTestId("beta-nav-tracker"));
    expect(screen.getByTestId("beta-modal-tracker")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Applications Tracker/i })).toBeInTheDocument();
  });
});
