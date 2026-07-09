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

  test("about architecture page", async ({ page }) => {
    await settleUi(page);
    await mockApi(page);
    await page.goto("/about");
    await expect(page.getByTestId("about-funnel")).toBeVisible();
    await expect(page.getByText(/Score formula/i)).toBeVisible();
  });
});
