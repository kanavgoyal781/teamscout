import { expect, test } from "@playwright/test";

import { mockApi } from "./fixtures";
import { settleUi, useDarkTheme, useLightTheme, waitForOpacityOne } from "./helpers";

async function runFeature2Shots(
  page: import("@playwright/test").Page,
  suffix: "" | "-dark",
) {
  await mockApi(page);
  await page.goto("/library");

  await expect(page.getByTestId("library-list")).toBeVisible();
  await expect(page.getByText("ada.pdf")).toBeVisible();
  await waitForOpacityOne(page, "library-ingest");

  await page.screenshot({
    path: `public/screenshots/05-library${suffix}.png`,
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
    path: `public/screenshots/06-resume-comparison${suffix}.png`,
    fullPage: true,
  });
}

test.describe("Feature 2 — library → paste JD → best resume", () => {
  test("paste JD and top-3 comparison with screenshots (light)", async ({ page }) => {
    await useLightTheme(page);
    await settleUi(page, "light");
    await runFeature2Shots(page, "");
  });

  test("paste JD and top-3 comparison with screenshots (dark)", async ({ page }) => {
    await useDarkTheme(page);
    await settleUi(page, "dark");
    await runFeature2Shots(page, "-dark");
  });

  test("empty library instruction", async ({ page }) => {
    await settleUi(page);
    await mockApi(page, { libraryEmpty: true });
    await page.goto("/library");
    await expect(page.getByText(/No resumes in library yet/i)).toBeVisible();
  });

  // About coverage lives in e2e/about.spec.ts (stats + journeys + detail).
});
