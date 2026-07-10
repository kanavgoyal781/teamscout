import { describe, expect, it } from "vitest";

import {
  materializeTournamentReason,
  stripWeightNotation,
} from "./ResumeRecommendations";

describe("tournament reason hygiene", () => {
  it("strips internal weight notation", () => {
    expect(stripWeightNotation("Prefer Python (w=2.0) over nice skills")).toBe(
      "Prefer Python over nice skills",
    );
  });

  it("does not remap Resume A/B by rank (backend already materializes pair filenames)", () => {
    // Residual A/B must stay — pair-local flip means rank order is wrong for mapping.
    expect(materializeTournamentReason("Resume A beats Resume B on antibodies (w=2.0)")).toBe(
      "Resume A beats Resume B on antibodies",
    );
    expect(
      materializeTournamentReason("antibody_expert.pdf shows phage display depth"),
    ).toBe("antibody_expert.pdf shows phage display depth");
  });
});
