import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import HealthBanner from "./HealthBanner";

function renderBanner() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <HealthBanner />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.clearAllTimers();
});

describe("HealthBanner", () => {
  it("does not render while the initial health fetch is in flight", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise(() => {})),
    );

    renderBanner();
    expect(screen.queryByTestId("health-banner")).not.toBeInTheDocument();
  });

  it("renders a red banner when checks are missing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        headers: new Headers(),
        json: async () => ({
          ok: false,
          db: true,
          checks: {
            llm: "missing",
            embeddings: "missing",
            jobs_api: "missing",
            sumble: "missing",
            google_drive: "missing",
          },
        }),
      }),
    );

    renderBanner();

    await waitFor(() => {
      expect(screen.getByTestId("health-banner")).toBeInTheDocument();
    });
    expect(screen.getByText(/llm missing/i)).toBeInTheDocument();
    expect(screen.getByText(/LLM_API_KEY/i)).toBeInTheDocument();
  });

  it("parses degraded health on HTTP 503 without calling it unreachable", async () => {
    // Production backend returns 503 when ok=false — still a valid health payload.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        statusText: "Service Unavailable",
        headers: new Headers(),
        json: async () => ({
          ok: false,
          db: true,
          version: "dev",
          checks: {
            llm: "configured",
            embeddings: "configured",
            jobs_api: "missing",
            sumble: "configured",
            google_drive: "missing",
          },
          optional_checks: ["google_drive"],
        }),
      }),
    );

    renderBanner();

    await waitFor(() => {
      expect(screen.getByTestId("health-banner")).toBeInTheDocument();
    });
    const banner = screen.getByTestId("health-banner");
    expect(within(banner).getByText(/jobs api missing/i)).toBeInTheDocument();
    expect(within(banner).getByText(/JOBS_API_KEY/i)).toBeInTheDocument();
    expect(within(banner).queryByText(/backend unreachable/i)).not.toBeInTheDocument();
  });

  it("renders a red banner when the database is failing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        headers: new Headers(),
        json: async () => ({
          ok: false,
          db: false,
          checks: {
            llm: "configured",
            embeddings: "configured",
            jobs_api: "configured",
            sumble: "configured",
            google_drive: "configured",
          },
        }),
      }),
    );

    renderBanner();

    await waitFor(() => {
      expect(screen.getByText(/database failing/i)).toBeInTheDocument();
    });
  });

  it("renders a red banner when the backend is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network down")));

    renderBanner();

    await waitFor(() => {
      expect(screen.getByText(/backend unreachable/i)).toBeInTheDocument();
    });
  });

  it("stays hidden when health is fully green", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        headers: new Headers(),
        json: async () => ({
          ok: true,
          db: true,
          checks: {
            llm: "configured",
            embeddings: "configured",
            jobs_api: "configured",
            sumble: "configured",
            google_drive: "configured",
          },
        }),
      }),
    );

    const { container } = renderBanner();

    await waitFor(() => {
      expect(within(container).queryByTestId("health-banner")).not.toBeInTheDocument();
    });
  });

  it("stays hidden when only optional google drive is missing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        headers: new Headers(),
        json: async () => ({
          ok: true,
          db: true,
          optional_checks: ["google_drive"],
          checks: {
            llm: "configured",
            embeddings: "configured",
            jobs_api: "configured",
            sumble: "configured",
            google_drive: "missing",
          },
        }),
      }),
    );

    const { container } = renderBanner();

    await waitFor(() => {
      expect(within(container).queryByTestId("health-banner")).not.toBeInTheDocument();
    });
  });
});
