import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";

// Controllable reduced-motion: default true so detail-panel tests avoid mode="wait" delays.
const reducedMotion = { current: true };

vi.mock("framer-motion", async () => {
  const actual = await vi.importActual<typeof import("framer-motion")>("framer-motion");
  return {
    ...actual,
    useReducedMotion: () => reducedMotion.current,
  };
});

import AboutArchitecture from "./AboutArchitecture";

vi.mock("../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../lib/api")>("../lib/api");
  return {
    ...actual,
    fetchPublicStats: vi.fn().mockResolvedValue({
      jobs_ranked_total: 10,
      resumes_parsed_total: 5,
      teams_discovered_total: 2,
      median_rank_latency_ms: 100,
      total_llm_cost_usd: 0.5,
    }),
  };
});

function renderAbout(ui: ReactElement = <AboutArchitecture />) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("AboutArchitecture detail panel focus", () => {
  beforeEach(() => {
    reducedMotion.current = true;
    Element.prototype.scrollIntoView = vi.fn();
  });

  it("moves focus to the close button when opening a detail", async () => {
    renderAbout();

    fireEvent.click(screen.getByTestId("about-card-f1"));

    await waitFor(() => {
      expect(screen.getByTestId("about-detail")).toBeInTheDocument();
    });

    const close = screen.getByRole("button", { name: "Close details" });
    expect(document.activeElement).toBe(close);
  });

  it("keeps focus on the close button after switching f1 → f2 (mode=wait remount)", async () => {
    renderAbout();

    fireEvent.click(screen.getByTestId("about-card-f1"));
    await waitFor(() => {
      expect(screen.getByTestId("about-detail")).toBeInTheDocument();
    });
    expect(screen.getByRole("heading", { level: 3, name: /Feature 1/i })).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("about-card-f2"));
    await waitFor(() => {
      expect(screen.getByRole("heading", { level: 3, name: /Feature 2/i })).toBeInTheDocument();
    });

    const close = screen.getByRole("button", { name: "Close details" });
    expect(document.activeElement).toBe(close);
    // Single panel instance — one close control, one id host
    expect(screen.getAllByTestId("about-detail")).toHaveLength(1);
  });

  it("scrolls the panel into view on open", async () => {
    const scrollSpy = vi.spyOn(Element.prototype, "scrollIntoView");
    renderAbout();

    fireEvent.click(screen.getByTestId("about-card-f1"));
    await waitFor(() => {
      expect(screen.getByTestId("about-detail")).toBeInTheDocument();
    });

    expect(scrollSpy).toHaveBeenCalled();
    const withOpts = scrollSpy.mock.calls.find(
      (c) => c[0] && typeof c[0] === "object" && "block" in (c[0] as object),
    );
    expect(withOpts?.[0]).toMatchObject({ block: "nearest" });
  });

  it("surfaces ML ops and deploy narrative sections", () => {
    renderAbout();
    expect(screen.getByTestId("about-mlops")).toBeInTheDocument();
    expect(screen.getByTestId("about-deploy")).toBeInTheDocument();
    expect(screen.getByText(/Lightweight ML ops/i)).toBeInTheDocument();
    expect(screen.getByText(/One browser, one API, one volume/i)).toBeInTheDocument();
  });

  it("opens deploy topology detail from the deploy plate", async () => {
    renderAbout();
    fireEvent.click(screen.getByTestId("about-card-deploy_topology"));
    await waitFor(() => {
      expect(screen.getByTestId("about-detail")).toBeInTheDocument();
    });
    expect(screen.getByRole("heading", { level: 3, name: /Deploy topology/i })).toBeInTheDocument();
  });

  it("renders the product film plate with multi-shot honesty copy (poster when reduced motion)", () => {
    renderAbout();
    const plate = screen.getByTestId("about-product-video");
    expect(plate).toBeInTheDocument();
    // Reduced-motion mock → static poster, no playback control, no video element
    expect(screen.queryByTestId("about-product-video-el")).not.toBeInTheDocument();
    expect(screen.queryByTestId("about-product-video-playback")).not.toBeInTheDocument();
    const poster = plate.querySelector("img.about-video");
    expect(poster).toBeTruthy();
    expect(poster?.getAttribute("src")).toBe("/videos/teamscout-match-01-poster.jpg");
    expect(screen.getByText(/AI-generated · still frame \(reduced motion\)/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Product film — resume → ranked fits → hiring-team constellation/i),
    ).toBeInTheDocument();
  });

  it("opens product motion detail from the video plate", async () => {
    renderAbout();
    fireEvent.click(screen.getByTestId("about-product-video"));
    await waitFor(() => {
      expect(screen.getByTestId("about-detail")).toBeInTheDocument();
    });
    expect(
      screen.getByRole("heading", { level: 3, name: /Product motion/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/teamscout-match-01\.mp4/i)).toBeInTheDocument();
    expect(screen.getByText(/not a production screen recording/i)).toBeInTheDocument();
  });
});

describe("AboutArchitecture product film multi-shot (motion allowed)", () => {
  beforeEach(() => {
    reducedMotion.current = false;
    Element.prototype.scrollIntoView = vi.fn();
    // framer-motion whileInView needs IntersectionObserver (absent in jsdom)
    class IOStub {
      observe() {}
      unobserve() {}
      disconnect() {}
      takeRecords() {
        return [];
      }
    }
    vi.stubGlobal("IntersectionObserver", IOStub);
    HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue(undefined);
    HTMLMediaElement.prototype.pause = vi.fn();
  });

  it("mounts shot 1 video with correct src/poster and sibling playback control", () => {
    renderAbout();
    const video = screen.getByTestId("about-product-video-el");
    expect(video).toHaveAttribute("data-shot", "resume");
    expect(video).toHaveAttribute("src", "/videos/teamscout-match-01.mp4");
    expect(video).toHaveAttribute("poster", "/videos/teamscout-match-01-poster.jpg");
    expect(screen.getByText(/Fig\. 1a/i)).toBeInTheDocument();
    expect(screen.getByText(/Resume card/i)).toBeInTheDocument();
    expect(screen.getByText(/shot 1 of 3/i)).toBeInTheDocument();

    const frame = screen.getByTestId("about-product-video");
    const playback = screen.getByTestId("about-product-video-playback");
    expect(frame.contains(playback)).toBe(false);
    expect(frame.parentElement?.contains(playback)).toBe(true);
    expect(playback).toHaveAttribute("aria-label", "Pause product video");
  });

  it("advances shot on ended and wraps after shot 3", async () => {
    renderAbout();

    fireEvent.ended(screen.getByTestId("about-product-video-el"));
    await waitFor(() => {
      expect(screen.getByTestId("about-product-video-el")).toHaveAttribute("data-shot", "matches");
    });
    expect(screen.getByText(/Fig\. 1b/i)).toBeInTheDocument();
    expect(screen.getByText(/Ranked fits/i)).toBeInTheDocument();
    expect(screen.getByText(/shot 2 of 3/i)).toBeInTheDocument();
    expect(screen.getByTestId("about-product-video-el")).toHaveAttribute(
      "src",
      "/videos/teamscout-match-02.mp4",
    );

    fireEvent.ended(screen.getByTestId("about-product-video-el"));
    await waitFor(() => {
      expect(screen.getByTestId("about-product-video-el")).toHaveAttribute("data-shot", "team");
    });
    expect(screen.getByText(/Fig\. 1c/i)).toBeInTheDocument();
    expect(screen.getByText(/shot 3 of 3/i)).toBeInTheDocument();

    fireEvent.ended(screen.getByTestId("about-product-video-el"));
    await waitFor(() => {
      expect(screen.getByTestId("about-product-video-el")).toHaveAttribute("data-shot", "resume");
    });
    expect(screen.getByText(/shot 1 of 3/i)).toBeInTheDocument();
  });

  it("pause intent blocks autoplay on next shot remount; resume continues", async () => {
    const playMock = HTMLMediaElement.prototype.play as ReturnType<typeof vi.fn>;
    renderAbout();

    await waitFor(() => {
      expect(playMock).toHaveBeenCalled();
    });

    fireEvent.click(screen.getByTestId("about-product-video-playback"));
    expect(screen.getByTestId("about-product-video-playback")).toHaveAttribute(
      "aria-label",
      "Play product video",
    );
    expect(HTMLMediaElement.prototype.pause).toHaveBeenCalled();

    playMock.mockClear();
    fireEvent.ended(screen.getByTestId("about-product-video-el"));
    await waitFor(() => {
      expect(screen.getByTestId("about-product-video-el")).toHaveAttribute("data-shot", "matches");
    });
    // Intent is pause — remount must not autoplay
    expect(playMock).not.toHaveBeenCalled();
    // Control still reflects intent (no flicker to Pause just because shot advanced)
    expect(screen.getByTestId("about-product-video-playback")).toHaveAttribute(
      "aria-label",
      "Play product video",
    );

    fireEvent.click(screen.getByTestId("about-product-video-playback"));
    expect(screen.getByTestId("about-product-video-playback")).toHaveAttribute(
      "aria-label",
      "Pause product video",
    );
    expect(playMock).toHaveBeenCalled();
  });

  it("announces shot changes via polite live region on figcaption", () => {
    renderAbout();
    const live = document.querySelector(".about-video-plate-label");
    expect(live).toHaveAttribute("aria-live", "polite");
  });

  it("shows Play after exhausted autoplay failures so one gesture restarts", async () => {
    HTMLMediaElement.prototype.play = vi.fn().mockRejectedValue(new DOMException("NotAllowedError"));
    renderAbout();

    // Intent starts as play — control still says Pause while retry is in flight
    expect(screen.getByTestId("about-product-video-playback")).toHaveAttribute(
      "aria-label",
      "Pause product video",
    );

    // After first reject + delayed retry reject, intent resets to Play
    await waitFor(
      () => {
        expect(screen.getByTestId("about-product-video-playback")).toHaveAttribute(
          "aria-label",
          "Play product video",
        );
      },
      { timeout: 1500 },
    );

    const playMock = HTMLMediaElement.prototype.play as ReturnType<typeof vi.fn>;
    playMock.mockClear();
    playMock.mockResolvedValue(undefined);
    fireEvent.click(screen.getByTestId("about-product-video-playback"));
    expect(screen.getByTestId("about-product-video-playback")).toHaveAttribute(
      "aria-label",
      "Pause product video",
    );
    expect(playMock).toHaveBeenCalled();
  });
});
