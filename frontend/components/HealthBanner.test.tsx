import { render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import HealthBanner from "./HealthBanner";

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

    render(<HealthBanner />);
    expect(screen.queryByTestId("health-banner")).not.toBeInTheDocument();
  });

  it("renders a red banner when checks are missing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
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

    render(<HealthBanner />);

    await waitFor(() => {
      expect(screen.getByTestId("health-banner")).toBeInTheDocument();
    });
    expect(screen.getByText(/llm missing/i)).toBeInTheDocument();
  });

  it("renders a red banner when the database is failing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
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

    render(<HealthBanner />);

    await waitFor(() => {
      expect(screen.getByText(/database failing/i)).toBeInTheDocument();
    });
  });

  it("renders a red banner when the backend is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network down")));

    render(<HealthBanner />);

    await waitFor(() => {
      expect(screen.getByText(/backend unreachable/i)).toBeInTheDocument();
    });
  });

  it("stays hidden when health is fully green", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
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

    const { container } = render(<HealthBanner />);

    await waitFor(() => {
      expect(within(container).queryByTestId("health-banner")).not.toBeInTheDocument();
    });
  });

  it("stays hidden when only optional google drive is missing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
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

    const { container } = render(<HealthBanner />);

    await waitFor(() => {
      expect(within(container).queryByTestId("health-banner")).not.toBeInTheDocument();
    });
  });
});