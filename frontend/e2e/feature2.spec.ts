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

  // M26: pathological filenames middle-truncate without horizontal overflow
  const pathName = "Kanav_Data_Science_______.pdf";
  // title attr carries full name; visible text is truncated
  await expect(page.locator(`.filename-trunc[title="${pathName}"]`).first()).toBeVisible();
  const listBox = page.getByTestId("library-list");
  const overflowX = await listBox.evaluate((el) => {
    const s = window.getComputedStyle(el);
    return el.scrollWidth <= el.clientWidth + 2 || s.overflowX === "auto" || s.overflowX === "scroll";
  });
  expect(overflowX).toBe(true);
  // No child stretches the page body beyond viewport width significantly
  const bodyOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(bodyOverflow).toBeLessThan(40);

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

  // Pathological winner filename truncated with full title on hover
  await expect(
    page.getByTestId("recommendation-0").locator(".filename-trunc").first(),
  ).toHaveAttribute("title", "Kanav Goyal_AI (2) (3).pdf");

  await page.screenshot({
    path: `public/screenshots/06-resume-comparison${suffix}.png`,
    fullPage: true,
  });
}

test("pathological library filenames do not break layout", async ({ page }) => {
  await useLightTheme(page);
  await settleUi(page, "light");
  await mockApi(page);
  await page.goto("/library");
  await expect(page.getByTestId("library-list")).toBeVisible();
  const full = "Kanav_Data_Science_______.pdf";
  const el = page.locator(`.filename-trunc[title="${full}"]`).first();
  await expect(el).toBeVisible();
  const box = await el.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.width).toBeLessThan(480);
  const text = await el.innerText();
  expect(text.length).toBeLessThan(full.length);
  expect(text).toContain("…");
  // Second pathological form with spaces / paren copies
  const full2 = "Kanav Goyal_AI (2) (3).pdf";
  await expect(page.locator(`.filename-trunc[title="${full2}"]`).first()).toBeVisible();
  const bodyOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(bodyOverflow).toBeLessThan(40);
});

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
