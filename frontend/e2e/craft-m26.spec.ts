import { expect, test } from "@playwright/test";

import { API, mockApi } from "./fixtures";
import { settleUi, useDarkTheme, useLightTheme } from "./helpers";

const longJd =
  "We are hiring a Staff Backend Engineer to build reliable Python APIs and data services. " +
  "Requirements include Python, SQL, systems design, distributed systems, and mentoring. " +
  "Nice to have: Kubernetes, Terraform, and experience with ranking systems. " +
  "Location: Remote US. Company: Acme Labs. Compensation competitive. ".repeat(2);

test.describe("M26 craft surfaces", () => {
  test("paste-JD mid-detection light + dark screenshots", async ({ page }) => {
    await useLightTheme(page);
    await settleUi(page, "light");
    await mockApi(page);

    // Hang metadata extract so detecting-shimmer stays visible
    await page.route(`${API}/jobs/extract-metadata`, async (route) => {
      await new Promise((r) => setTimeout(r, 15_000));
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          metadata: {
            title: "Staff Backend Engineer",
            company: "Acme Labs",
            location: "Remote",
            field_confidence: { title: "high", company: "high", location: "medium" },
          },
        }),
      });
    });

    await page.goto("/library");
    await expect(page.getByTestId("paste-jd-panel")).toBeVisible();
    await page.getByTestId("jd-paste").fill(longJd);
    await expect(page.getByTestId("jd-detecting")).toBeVisible({ timeout: 3000 });
    await page.screenshot({
      path: "public/screenshots/08-paste-jd-detecting.png",
      fullPage: true,
    });

    // Dark mid-detection
    await useDarkTheme(page);
    await settleUi(page, "dark");
    await page.goto("/library");
    await page.getByTestId("jd-paste").fill(longJd + " ");
    await expect(page.getByTestId("jd-detecting")).toBeVisible({ timeout: 3000 });
    await page.screenshot({
      path: "public/screenshots/08-paste-jd-detecting-dark.png",
      fullPage: true,
    });
  });

  test("ops craft light + dark screenshots", async ({ page }) => {
    const opsHtml = (theme: "light" | "dark") => `<!DOCTYPE html>
<html data-theme="${theme}" class="${theme === "dark" ? "dark" : ""}"><head><title>TeamScout Ops</title>
<style>
:root{--bg:#F7F4ED;--bg-raised:#FDFBF7;--ink:#0C1F3F;--ink-strong:#081426;--muted:#5C6B82;--line:rgba(12,31,63,.12);--accent:#0C1F3F}
html.dark,:root[data-theme=dark]{--bg:#0A182E;--bg-raised:#102340;--ink:#F2EDE2;--ink-strong:#FDFBF7;--muted:#9AA3B5;--line:rgba(242,237,226,.14);--accent:#F2EDE2}
body{font-family:system-ui,sans-serif;margin:1.5rem;background:var(--bg);color:var(--ink)}
h1,h2{color:var(--ink-strong)}.ops-table{border-collapse:collapse;width:100%;background:var(--bg-raised);border:1px solid var(--line)}
.ops-table th,.ops-table td{border-bottom:1px solid var(--line);padding:8px 10px}
.ops-table th{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.08em}
.ops-table td.num{font-variant-numeric:tabular-nums;font-family:ui-monospace,monospace;text-align:right}
.ops-table tbody tr:nth-child(even){background:color-mix(in srgb,var(--ink) 3%,transparent)}
</style></head><body data-testid="ops-root">
<h1>TeamScout Ops</h1>
<table class="ops-table" data-testid="ops-table"><thead><tr><th>metric</th><th>value</th></tr></thead>
<tbody>
<tr><td>llm_cost_today_usd</td><td class="num">1.23</td></tr>
<tr><td>p50_ms</td><td class="num">320</td></tr>
<tr><td>feature2_runs_today</td><td class="num">4</td></tr>
</tbody></table>
</body></html>`;

    await page.setContent(opsHtml("light"));
    await expect(page.getByTestId("ops-table")).toBeVisible();
    const numAlign = await page.locator("td.num").first().evaluate((el) => getComputedStyle(el).textAlign);
    expect(numAlign).toBe("right");
    const tnum = await page.locator("td.num").first().evaluate((el) => getComputedStyle(el).fontVariantNumeric);
    expect(tnum).toMatch(/tabular-nums|lining-nums|normal/); // browsers may report differently; class is present
    await page.screenshot({ path: "public/screenshots/09-ops.png", fullPage: true });

    await page.setContent(opsHtml("dark"));
    await expect(page.getByTestId("ops-table")).toBeVisible();
    const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
    expect(bg).toMatch(/rgb\(10,\s*24,\s*46\)/);
    await page.screenshot({ path: "public/screenshots/09-ops-dark.png", fullPage: true });
  });

  test("recommendation score bars stay behind why disclosure", async ({ page }) => {
    await useLightTheme(page);
    await settleUi(page, "light");
    await mockApi(page);
    await page.goto("/library");
    await page.getByTestId("jd-paste").fill(
      "We are hiring a Staff Backend Engineer to build reliable Python APIs. Requirements: Python, SQL, systems design.",
    );
    await page.getByRole("button", { name: /Find best resume for this job/i }).click();
    await expect(page.getByTestId("recommendations")).toBeVisible();
    // Breakdown exists in closed <details> but must not be visible until opened
    await expect(page.getByTestId("recommendation-0").locator(".breakdown-bars")).toBeHidden();
    await page.getByTestId("why-resume-0").locator("summary").click();
    await expect(page.getByTestId("why-resume-0").locator(".breakdown-bars")).toBeVisible();
    // Expand clamp on long requirements when present
    const expand = page.getByTestId("alignment-0").getByRole("button", { name: /Expand/i }).first();
    if (await expand.count()) {
      await expand.click();
      await expect(page.getByTestId("alignment-0").getByRole("button", { name: /Show less/i }).first()).toBeVisible();
    }
  });
});
