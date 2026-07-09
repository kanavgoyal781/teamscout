import type { Page } from "@playwright/test";
import { expect } from "@playwright/test";

/** Force dark product theme via cookie before navigation. */
export async function useDarkTheme(page: Page) {
  await page.context().addCookies([
    {
      name: "teamscout-theme",
      value: "dark",
      domain: "127.0.0.1",
      path: "/",
    },
  ]);
}

/** Prefer reduced motion so entrance stagger does not capture washed-out shells. */
export async function settleUi(page: Page) {
  // colorScheme only — entrance motion is skipped under navigator.webdriver
  await page.emulateMedia({ colorScheme: "dark" });
  await page.evaluate(async () => {
    if (document.fonts?.ready) {
      await document.fonts.ready;
    }
  });
}

export async function waitForOpacityOne(page: Page, testId: string) {
  await expect(page.getByTestId(testId)).toBeVisible();
  await expect
    .poll(async () =>
      page.getByTestId(testId).evaluate((el) => window.getComputedStyle(el).opacity),
    )
    .toBe("1");
  // Allow score-ring SVG + layout paint after opacity settles
  await page.waitForTimeout(200);
}
