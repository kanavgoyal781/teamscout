import { expect, test } from "@playwright/test";
import path from "path";

import { degraded, mockApi } from "./fixtures";
import { settleUi, useDarkTheme, useLightTheme, waitForOpacityOne } from "./helpers";

const samplePdf = path.join(__dirname, "../../samples/sample_resume.pdf");

async function runFeature1HappyPath(
  page: import("@playwright/test").Page,
  suffix: "" | "-dark",
) {
  await mockApi(page);
  await page.goto("/");
  await expect(page.getByTestId("resume-wizard")).toBeVisible();
  await waitForOpacityOne(page, "resume-wizard");

  await page.screenshot({
    path: `public/screenshots/01-wizard-upload${suffix}.png`,
    fullPage: true,
  });

  await page.locator('input[name="resume"]').setInputFiles(samplePdf);
  await expect(page.getByTestId("file-preview")).toBeVisible();
  await page.getByRole("button", { name: /upload & parse/i }).click();
  await expect(page.getByTestId("profile-confirm")).toBeVisible();
  await waitForOpacityOne(page, "profile-confirm");

  await page.screenshot({
    path: `public/screenshots/02-profile-confirm${suffix}.png`,
    fullPage: true,
  });

  await page.getByRole("button", { name: /confirm profile/i }).click();
  await page.getByTestId("search-jobs").click();
  await expect(page.getByTestId("job-results")).toBeVisible();
  await expect(page.getByTestId("job-card-0")).toContainText("Staff Backend Engineer");
  await expect(page.getByText("87").first()).toBeVisible();
  await waitForOpacityOne(page, "job-card-0");
  await waitForOpacityOne(page, "job-card-1");
  // Craft pass: open why-panel on first card for screenshot
  await page.getByTestId("job-card-0").getByText("Why this match").click();
  await expect(page.getByTestId("job-card-0").locator(".breakdown-bars")).toBeVisible();

  await page.screenshot({
    path: `public/screenshots/03-job-matches${suffix}.png`,
    fullPage: true,
  });

  await page.getByTestId("find-team-0").click();
  await expect(page.getByLabel("Wizard progress").getByText("Team")).toBeVisible();
  await page.getByRole("button", { name: /extract team/i }).click();
  await expect(page.getByTestId("extraction-card")).toBeVisible();
  await page.getByTestId("confirm-find-team").click();
  await expect(page.getByTestId("contact-list")).toBeVisible();
  await expect(page.getByTestId("search-path")).toContainText("Matched posted role");
  await waitForOpacityOne(page, "team-panel");

  await page.screenshot({
    path: `public/screenshots/04-team-discovery${suffix}.png`,
    fullPage: true,
  });

  await page.getByRole("button", { name: /reveal email — preview cost/i }).click();
  await page.getByRole("button", { name: /confirm reveal/i }).click();
  await expect(page.getByText("jordan.lee@acme.example")).toBeVisible();
}

test.describe("Feature 1 — resume → jobs → team", () => {
  test("happy path with screenshots (light)", async ({ page }) => {
    await useLightTheme(page);
    await settleUi(page, "light");
    await runFeature1HappyPath(page, "");
  });

  test("happy path with screenshots (dark)", async ({ page }) => {
    await useDarkTheme(page);
    await settleUi(page, "dark");
    await runFeature1HappyPath(page, "-dark");
  });

  test("shows health degradation with env keys", async ({ page }) => {
    await settleUi(page);
    await mockApi(page, { health: degraded });
    await page.goto("/");
    await expect(page.getByTestId("health-banner")).toBeVisible();
    await expect(page.getByTestId("health-banner")).toContainText("LLM_API_KEY");
    await expect(page.getByTestId("health-banner")).toContainText("SUMBLE_API_KEY");
  });

  test("search error surfaces toast with request id", async ({ page }) => {
    await settleUi(page);
    await mockApi(page, { searchError: true });
    await page.goto("/");
    await page.locator('input[name="resume"]').setInputFiles(samplePdf);
    await page.getByRole("button", { name: /upload & parse/i }).click();
    await expect(page.getByTestId("profile-confirm")).toBeVisible();
    await page.getByRole("button", { name: /confirm profile/i }).click();
    await page.getByTestId("search-jobs").click();
    await expect(page.getByText(/Jobs API is not configured/i)).toBeVisible();
    await expect(page.getByText(/req-e2e-test/i)).toBeVisible();
  });

  test("empty job search shows empty state", async ({ page }) => {
    await settleUi(page);
    await mockApi(page, { searchEmpty: true });
    await page.goto("/");
    await page.locator('input[name="resume"]').setInputFiles(samplePdf);
    await page.getByRole("button", { name: /upload & parse/i }).click();
    await expect(page.getByTestId("profile-confirm")).toBeVisible();
    await page.getByRole("button", { name: /confirm profile/i }).click();
    await page.getByTestId("search-jobs").click();
    await expect(page.getByTestId("job-results-empty")).toBeVisible();
    await expect(page.getByText(/No ranked jobs matched/i)).toBeVisible();
  });
});
