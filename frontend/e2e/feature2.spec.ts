import { expect, test } from "@playwright/test";

import { mockApi } from "./fixtures";
import { settleUi, useDarkTheme, waitForOpacityOne } from "./helpers";

test.describe("Feature 2 — library → best resume", () => {
  test("intent search and top-3 comparison with screenshots", async ({ page }) => {
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

    await page.getByLabel("Desired role").fill("Staff Backend Engineer");
    await page.getByTestId("intent-search-submit").click();
    await expect(page.getByTestId("intent-jobs")).toBeVisible();
    await page.getByTestId("pick-resume-0").click();
    await expect(page.getByTestId("recommendations")).toBeVisible();
    await expect(page.getByTestId("recommendation-0")).toHaveClass(/winner/);
    await expect(page.getByText("Best match")).toBeVisible();
    await expect(page.getByText("✓").first()).toBeVisible();
    // F2 score bars show Experience (not empty Recency)
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

  test("empty intent search shows empty state", async ({ page }) => {
    await settleUi(page);
    await mockApi(page, { intentEmpty: true });
    await page.goto("/library");
    await page.getByLabel("Desired role").fill("Staff Backend Engineer");
    await page.getByTestId("intent-search-submit").click();
    await expect(page.getByTestId("intent-jobs-empty")).toBeVisible();
    await expect(
      page.getByTestId("intent-jobs-empty").getByText(/No jobs matched this intent/i),
    ).toBeVisible();
  });

  test("about architecture page", async ({ page }) => {
    await settleUi(page);
    await mockApi(page);
    await page.goto("/about");
    await expect(page.getByTestId("about-funnel")).toBeVisible();
    await expect(page.getByText(/Score formula/i)).toBeVisible();
  });
});
