import { expect, test } from "@playwright/test";

import { mockApi } from "./fixtures";
import { settleUi, useDarkTheme, waitForOpacityOne } from "./helpers";

test.describe("Feature 2 — library → paste JD → best resume", () => {
  test("paste JD and top-3 comparison with screenshots", async ({ page }) => {
    await useDarkTheme(page);
    await settleUi(page);
    await mockApi(page);
    await page.goto("/library");

    await expect(page.getByTestId("library-list")).toBeVisible();
    await expect(page.getByText("ada.pdf")).toBeVisible();
    await waitForOpacityOne(page, "library-ingest");

    await page.screenshot({
      path: "public/screenshots/05-library.png",
      fullPage: true,
    });

    await page.getByTestId("jd-paste").fill(
      "We are hiring a Staff Backend Engineer to build reliable Python APIs. " +
        "Requirements: Python, SQL, systems design. Nice to have: Kubernetes.",
    );
    await page.getByRole("button", { name: /Find best resume for this job/i }).click();
    await expect(page.getByTestId("recommendations")).toBeVisible();
    await expect(page.getByTestId("recommendation-0")).toHaveClass(/winner/);
    await expect(page.getByText("Best match")).toBeVisible();
    await expect(page.getByText("✓").first()).toBeVisible();
    await expect(page.getByText("Experience").first()).toBeVisible();
    // Post-PR-1: Coverage label, Overall match ring, tournament badge when override ran.
    await expect(page.getByTestId("coverage-label-0")).toContainText(/Coverage/i);
    await expect(page.getByText("Overall match").first()).toBeVisible();
    await expect(page.getByTestId("tournament-override-badge")).toContainText(
      /Ranked by close-call tournament/i,
    );
    await expect(page.getByTestId("tournament-cost")).toContainText(/Close-call tournament/i);
    await waitForOpacityOne(page, "recommendation-0");
    await waitForOpacityOne(page, "recommendation-1");
    await waitForOpacityOne(page, "recommendation-2");

    await page.screenshot({
      path: "public/screenshots/06-resume-comparison.png",
      fullPage: true,
    });
  });

  test("empty library instruction", async ({ page }) => {
    await settleUi(page);
    await mockApi(page, { libraryEmpty: true });
    await page.goto("/library");
    await expect(page.getByText(/No resumes in library yet/i)).toBeVisible();
  });

  // About coverage lives in e2e/about.spec.ts (stats + journeys + detail).
});
