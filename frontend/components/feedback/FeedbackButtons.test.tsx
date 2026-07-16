import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import FeedbackButtons, { trackImplicitFeedback } from "../feedback/FeedbackButtons";

const postFeedback = vi.fn();

vi.mock("../../lib/api", () => ({
  postFeedback: (...args: unknown[]) => postFeedback(...args),
}));

afterEach(() => {
  postFeedback.mockReset();
});

describe("FeedbackButtons", () => {
  it("posts thumbs_up with profile_hash and disables after success", async () => {
    postFeedback.mockResolvedValue({
      id: "1",
      kind: "thumbs_up",
      target_type: "job_match",
      target_id: "job-1",
    });
    render(
      <FeedbackButtons
        targetType="job_match"
        targetId="job-1"
        profileHash="aaaaaaaaaaaaaaaa"
        scoreShown={88}
        testIdPrefix="fb"
      />,
    );
    fireEvent.click(screen.getByTestId("fb-up"));
    await waitFor(() => {
      expect(postFeedback).toHaveBeenCalledWith(
        expect.objectContaining({
          kind: "thumbs_up",
          target_type: "job_match",
          target_id: "job-1",
          profile_hash: "aaaaaaaaaaaaaaaa",
          score_shown: 88,
        }),
      );
    });
    expect(screen.getByTestId("fb-up")).toBeDisabled();
    expect(screen.getByTestId("fb-down")).toBeDisabled();
  });

  it("shows aria-live error and re-enables when POST fails", async () => {
    postFeedback.mockRejectedValue(new Error("fail"));
    render(
      <FeedbackButtons targetType="job_match" targetId="job-2" testIdPrefix="fb" />,
    );
    fireEvent.click(screen.getByTestId("fb-down"));
    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent(/couldn't save feedback/i);
    });
    expect(screen.getByTestId("fb-up")).not.toBeDisabled();
  });

  it("trackImplicitFeedback posts apply_click", async () => {
    postFeedback.mockResolvedValue({ id: "x", kind: "apply_click", target_type: "job_match", target_id: "j" });
    trackImplicitFeedback({
      kind: "apply_click",
      targetType: "job_match",
      targetId: "j",
      profileHash: "bbbbbbbbbbbbbbbb",
      scoreShown: 70,
    });
    await waitFor(() => {
      expect(postFeedback).toHaveBeenCalledWith(
        expect.objectContaining({
          kind: "apply_click",
          target_type: "job_match",
          target_id: "j",
          profile_hash: "bbbbbbbbbbbbbbbb",
        }),
      );
    });
  });
});
