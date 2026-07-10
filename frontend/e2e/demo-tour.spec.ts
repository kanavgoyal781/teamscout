import { expect, test } from "@playwright/test";

import { mockApi } from "./fixtures";
import { settleUi } from "./helpers";

// Keep in sync with components/tour/DemoTour.tsx TOUR_STEPS length
const TOUR_STEP_COUNT = 5;

test.describe("Demo tour", () => {
  test("keyboard-only tour completes without credit spend", async ({ page }) => {
    await settleUi(page);
    await mockApi(page);

    let findTeam = 0;
    let reveal = 0;
    page.on("request", (req) => {
      const u = req.url();
      if (req.method() === "POST" && u.includes("/find-team")) findTeam += 1;
      if (req.method() === "POST" && u.includes("/reveal-email")) reveal += 1;
    });

    await page.goto("/");

    await page.getByTestId("demo-tour-start").click();
    await expect(page.getByTestId("demo-tour")).toBeVisible();
    await expect(page.getByTestId("demo-tour")).toHaveAttribute("role", "dialog");
    await expect(page.getByTestId("demo-tour-step-label")).toHaveText(`Step 1 / ${TOUR_STEP_COUNT}`);
    await expect(page.getByTestId("demo-tour-card")).toContainText("Feature 1");
    // Always-mounted credit-gate anchor
    await expect(page.getByTestId("credit-confirm")).toBeVisible();

    for (let i = 0; i < TOUR_STEP_COUNT - 1; i++) {
      await page.keyboard.press("ArrowRight");
      await expect(page.getByTestId("demo-tour-step-label")).toHaveText(
        `Step ${i + 2} / ${TOUR_STEP_COUNT}`,
      );
    }

    await expect(page.getByTestId("demo-tour-card")).toContainText(/Stop before credit spend/i);
    await expect(page.getByTestId("demo-tour-next")).toHaveText(/Finish \(no credit spend\)/i);
    await page.keyboard.press("ArrowRight");

    await expect(page.getByTestId("demo-tour")).toHaveCount(0);
    expect(findTeam).toBe(0);
    expect(reveal).toBe(0);
    await expect(page.getByTestId("contact-list")).toHaveCount(0);
  });

  test("escape dismisses and restores focus to start control", async ({ page }) => {
    await settleUi(page);
    await mockApi(page);
    await page.goto("/");
    const start = page.getByTestId("demo-tour-start");
    await start.focus();
    await start.click();
    await expect(page.getByTestId("demo-tour")).toBeVisible();
    await expect(page.getByTestId("demo-tour-next")).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("demo-tour")).toHaveCount(0);
    await expect(start).toBeFocused();
  });
});
