"use client";

import { ThumbsDown, ThumbsUp } from "lucide-react";
import { useState } from "react";

import { postFeedback } from "../lib/api";
import type { FeedbackKind, FeedbackTargetType } from "../lib/types";

type FeedbackButtonsProps = {
  targetType: FeedbackTargetType;
  targetId: string;
  secondaryId?: string | null;
  profileHash?: string | null;
  jdHash?: string | null;
  scoreShown?: number | null;
  testIdPrefix?: string;
};

export default function FeedbackButtons({
  targetType,
  targetId,
  secondaryId = null,
  profileHash = null,
  jdHash = null,
  scoreShown = null,
  testIdPrefix = "feedback",
}: FeedbackButtonsProps) {
  const [sent, setSent] = useState<"up" | "down" | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send(kind: FeedbackKind, which: "up" | "down") {
    if (busy || sent) return;
    setBusy(true);
    setError(null);
    try {
      await postFeedback({
        kind,
        target_type: targetType,
        target_id: targetId,
        secondary_id: secondaryId,
        profile_hash: profileHash,
        jd_hash: jdHash,
        score_shown: scoreShown,
      });
      setSent(which);
    } catch {
      setSent(null);
      setError("Couldn't save feedback");
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className="feedback-btns" role="group" aria-label="Match feedback">
      <button
        type="button"
        className={`feedback-btn${sent === "up" ? " active" : ""}`}
        aria-label="Thumbs up"
        aria-pressed={sent === "up"}
        disabled={busy || sent !== null}
        data-testid={`${testIdPrefix}-up`}
        onClick={() => void send("thumbs_up", "up")}
      >
        <ThumbsUp size={14} aria-hidden />
      </button>
      <button
        type="button"
        className={`feedback-btn${sent === "down" ? " active" : ""}`}
        aria-label="Thumbs down"
        aria-pressed={sent === "down"}
        disabled={busy || sent !== null}
        data-testid={`${testIdPrefix}-down`}
        onClick={() => void send("thumbs_down", "down")}
      >
        <ThumbsDown size={14} aria-hidden />
      </button>
      {error ? (
        <span className="meta" role="status" aria-live="polite" style={{ fontSize: 12 }}>
          {error}
        </span>
      ) : null}
    </span>
  );
}

/** Fire-and-forget implicit signals (apply / find-team / compose). */
export function trackImplicitFeedback(payload: {
  kind: "apply_click" | "find_team_click" | "compose_opened";
  targetType: FeedbackTargetType;
  targetId: string;
  secondaryId?: string | null;
  profileHash?: string | null;
  jdHash?: string | null;
  scoreShown?: number | null;
}): void {
  void postFeedback({
    kind: payload.kind,
    target_type: payload.targetType,
    target_id: payload.targetId,
    secondary_id: payload.secondaryId ?? null,
    profile_hash: payload.profileHash ?? null,
    jd_hash: payload.jdHash ?? null,
    score_shown: payload.scoreShown ?? null,
  }).catch(() => {
    /* ignore */
  });
}
