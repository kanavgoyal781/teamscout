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

test("ops craft light + dark screenshots from real render_ops_html", async ({ page }) => {
    // Load stdlib-only shipped renderer by path — no FastAPI/deps (frontend CI has none).
    // Screenshots are capture-only artifacts (no pixel-diff baselines).
    const { execFileSync } = await import("node:child_process");
    const path = await import("node:path");
    const renderPath = path.join(__dirname, "../../backend/app/services/ops/html_render.py");
    const py = `
import importlib.util
from pathlib import Path
p = Path(${JSON.stringify(renderPath)})
spec = importlib.util.spec_from_file_location("ops_html_render", p)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)
stats = {
  "latency_by_operation": {"rerank": {"count": 3, "p50_ms": 320.7, "p95_ms": 410.2}},
  "error_rate_by_service": {"llm": {"errors": 1, "total": 10, "error_rate": 0.1}},
  "recent_traces": [{"created_at":"2026-07-16T12:00:00","operation":"rerank","status":"ok","latency_ms":120.4,"cost_usd":0.0123,"credits_used":None,"prompt_name":"rerank","prompt_version":"1","cache_hit":False,"error_type":None,"request_id":"r1"}],
  "total_cost_today_usd": 1.234, "llm_cost_today_usd": 1.234, "llm_ceiling_usd": 5.0,
  "sumble_credits_today": 12, "sumble_ceiling": 1000,
  "cost_per_feature1_run_usd": 0.4567, "feature1_runs_today": 3,
  "cost_per_feature2_run_usd": 0.1, "feature2_runs_today": 4,
  "embedding_cache_hit_rate": 0.55, "embedding_cache_hits": 11, "embedding_cache_total": 20,
  "workspace_llm_ceiling_usd": 1.0, "workspace_sumble_ceiling": 100,
  "workspace_usage_today": [{"workspace_id":"w1","llm_cost_usd":0.5,"sumble_credits":2}],
  "learning": {"evals_root":"/evals","feedback_counts":{"thumbs_up":2},"suites":[],"experiments":[]},
  "job_sources": [{"source":"jsearch","calls":5,"p50_ms":90.2,"p95_ms":120.0,"error_rate":0.0}],
  "m24_panel": "models=(single)",
}
print(mod.render_ops_html(stats))
`
    const html = execFileSync("python3", ["-c", py], {
      encoding: "utf-8",
      maxBuffer: 2_000_000,
    });
    expect(html).toContain("ops-table");
    expect(html).toMatch(/llm_cost_today_usd<\/td><td class="num">1\.23<\/td>/);
    expect(html).toContain("theme-bar");
    expect(html).toContain("Summary");

    await page.setContent(html);
    await expect(page.getByRole("heading", { name: "TeamScout Ops" })).toBeVisible();
    // Summary value cell for cost is .num and 2dp from real renderer
    const costCell = page.locator("td", { hasText: "llm_cost_today_usd" }).locator("xpath=following-sibling::td[1]");
    await expect(costCell).toHaveClass(/num/);
    await expect(costCell).toHaveText("1.23");
    const align = await costCell.evaluate((el) => getComputedStyle(el).textAlign);
    expect(align).toBe("right");
    await page.screenshot({ path: "public/screenshots/09-ops.png", fullPage: true });

    await page.getByRole("button", { name: "Dark" }).click();
    await expect(page.locator("html")).toHaveClass(/dark/);
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
