import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { LibraryResume } from "../../lib/types";
import LibraryIngestPanel from "./LibraryIngestPanel";

function synthResume(i: number): LibraryResume {
  return {
    id: `r-${i}`,
    filename: `resume-${i}.pdf`,
    content_hash: `hash-${i}`,
    source: "upload",
    profile: {
      name: `Person ${i}`,
      title: `Engineer ${i % 7}`,
      years_of_experience: 3,
      location: "Remote",
      skills: ["Python", "SQL"],
      work_experience: [],
      summary: "summary",
    },
    created_at: null,
    cluster_id: i % 10 === 0 ? `cluster-${Math.floor(i / 10)}` : `cluster-${Math.floor(i / 10)}`,
    cluster_label: null,
    cluster_size: null,
  };
}

describe("LibraryIngestPanel M21 scale", () => {
  it("renders 100 files in a ~5-row virtualized list without expanding all rows", () => {
    const resumes = Array.from({ length: 100 }, (_, i) => synthResume(i));
    const { container } = render(
      <LibraryIngestPanel
        resumes={resumes}
        loadingLibrary={false}
        uploading={false}
        syncing={false}
        driveUrl=""
        syncStatus={null}
        distinctVersions={20}
        cachedCount={90}
        parsedCount={10}
        onDriveUrlChange={() => {}}
        onUpload={(e) => e.preventDefault()}
        onDriveSync={(e) => e.preventDefault()}
      />,
    );

    const stats = screen.getByTestId("library-stats");
    expect(stats.textContent).toMatch(/100 files/);
    expect(stats.textContent).toMatch(/20 version/);
    expect(stats.textContent).toMatch(/90 cached/);
    expect(stats.textContent).toMatch(/10 newly parsed/);

    const list = screen.getByTestId("library-list");
    const maxH = (list as HTMLElement).style.maxHeight || getComputedStyle(list).maxHeight;
    // 5 * 44px = 220px default
    expect(maxH === "220px" || maxH === "220").toBe(true);

    // Virtualized: far fewer than 100 DOM rows at rest (collapsed clusters)
    const rows = list.querySelectorAll('[role="listitem"]');
    expect(rows.length).toBeLessThan(30);
    expect(rows.length).toBeGreaterThan(0);

    // Filter control present for a11y
    expect(screen.getByTestId("library-filter")).toBeInTheDocument();
    expect(screen.getByLabelText(/filter library/i)).toBeInTheDocument();

    // Cluster toggle is a button (keyboard accessible)
    const toggle = container.querySelector(".library-cluster-toggle");
    expect(toggle).toBeTruthy();
    expect(toggle?.getAttribute("aria-expanded")).toBe("false");
  });
});
