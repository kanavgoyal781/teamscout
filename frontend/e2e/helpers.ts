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

/** Force light product theme (M23 README/default shots). */
export async function useLightTheme(page: Page) {
  await page.context().addCookies([
    {
      name: "teamscout-theme",
      value: "light",
      domain: "127.0.0.1",
      path: "/",
    },
  ]);
}

/**
 * Prefer reduced motion so entrance stagger / CountUp settle immediately
 * for stable screenshots and chip assertions.
 * @param scheme OS color-scheme media; product theme still comes from cookie helpers.
 */
export async function settleUi(page: Page, scheme: "light" | "dark" = "light") {
  await page.emulateMedia({ colorScheme: scheme, reducedMotion: "reduce" });
}

/** After navigation: wait for fonts for screenshot fidelity. */
export async function settleFonts(page: Page) {
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
  await page.waitForTimeout(200);
}
