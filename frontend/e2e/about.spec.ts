import { expect, test } from "@playwright/test";

import { mockApi } from "./fixtures";
import { settleFonts, settleUi, useDarkTheme, waitForOpacityOne } from "./helpers";

test.describe("About page story", () => {
  test("hero stats, journeys, diagrams, principles", async ({ page }) => {
    await useDarkTheme(page);
    await settleUi(page);
    await mockApi(page);
    await page.goto("/about");
    await settleFonts(page);

    await expect(page.getByTestId("about-funnel")).toBeVisible();
    await expect(page.getByTestId("about-stats")).toBeVisible();
    await expect(page.getByTestId("stat-jobs-ranked")).toContainText("42");
    await expect(page.getByTestId("stat-resumes-parsed")).toContainText("17");
    await expect(page.getByTestId("stat-teams-found")).toContainText("9");
    await expect(page.getByTestId("stat-median-rank-ms")).toContainText("320");
    await expect(page.getByTestId("stat-llm-cost")).toContainText("1.2345");
    await expect(page.getByTestId("about-proof-strip")).toBeVisible();
    await expect(page.getByTestId("journey-flow")).toBeVisible();

    await page.getByTestId("journey-step-parse").click();
    await expect(page.getByText("services/parser.py · prompts/resume_schema.md")).toBeVisible();

    await expect(page.getByTestId("ranking-funnel-diagram")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Score formula" })).toBeVisible();
    await expect(page.getByTestId("mlops-cycle-diagram")).toBeVisible();
    await expect(page.getByTestId("about-principles")).toBeVisible();
    // No placeholder OWNER links when NEXT_PUBLIC_GITHUB_BASE unset
    await expect(page.locator('a[href*="OWNER/teamscout"]')).toHaveCount(0);
    await expect(page.getByTestId("about-footer")).toBeVisible();

    await waitForOpacityOne(page, "about-funnel");
    await page.screenshot({
      path: "public/screenshots/07-about.png",
      fullPage: true,
    });
  });

  test("detail panel still works after split", async ({ page }) => {
    await settleUi(page);
    await mockApi(page);
    await page.goto("/about");
    await page.getByTestId("about-card-f1").click();
    await expect(page.getByTestId("about-detail")).toBeVisible();
    await expect(page.getByRole("heading", { level: 3, name: /Feature 1/i })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("about-detail")).toHaveCount(0);
  });
});
