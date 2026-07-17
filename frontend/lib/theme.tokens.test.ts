import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = join(__dirname, "..");

function read(rel: string) {
  return readFileSync(join(ROOT, rel), "utf8");
}

describe("M23 design tokens", () => {
  const css = read("app/globals.css");

  it("defines cream + navy light tokens and dark inversion", () => {
    expect(css).toMatch(/--bg:\s*#F7F4ED/i);
    expect(css).toMatch(/--bg-raised:\s*#FDFBF7/i);
    expect(css).toMatch(/--ink:\s*#0C1F3F/i);
    expect(css).toMatch(/--ink-strong:\s*#081426/i);
    expect(css).toMatch(/--accent:\s*#0C1F3F/i);
    expect(css).toMatch(/--brass:\s*#7A6236/i);
    expect(css).toMatch(/html\.dark\s*\{/);
    expect(css).toMatch(/--bg:\s*#0A182E/i);
    expect(css).toMatch(/--brass:\s*#C4A86A/i);
    expect(css).toMatch(/--success:\s*#2F6B4F/i);
    expect(css).toMatch(/--warning:\s*#8A5A22/i);
    expect(css).toMatch(/--danger:\s*#8C3A32/i);
  });

  it("does not keep the old green accent palette", () => {
    expect(css.toLowerCase()).not.toMatch(/#3dd68c/);
    expect(css.toLowerCase()).not.toMatch(/#1f8f5a/);
  });

  it("has no neon chip / indigo facet fallbacks in CSS body", () => {
    expect(css).not.toMatch(/rgba\(\s*56\s*,\s*189\s*,\s*248/);
    expect(css).not.toMatch(/rgba\(\s*251\s*,\s*191\s*,\s*36/);
    expect(css).not.toMatch(/rgba\(\s*52\s*,\s*211\s*,\s*153/);
    expect(css).not.toMatch(/rgba\(\s*99\s*,\s*102\s*,\s*241/);
    // Use [\s\S] (not /s) so typecheck target ES2017 accepts these patterns.
    expect(css).toMatch(/\.chip-dup\s*\{[^}]*var\(--accent-soft\)/);
    expect(css).toMatch(/\.chip-salary-unknown\s*\{[^}]*var\(--warning-soft\)/);
    expect(css).toMatch(/\.chip-salary\s*\{[^}]*var\(--success-soft\)/);
    expect(css).toMatch(/\.facet-group button:hover\s*\{[^}]*var\(--surface-hover\)/);
    expect(css).toMatch(/\.filter-hint\s*\{[^}]*border-radius:\s*var\(--radius\)/);
  });

  it("uses single 10px radius and no decorative card shadows by default", () => {
    expect(css).toMatch(/--radius:\s*10px/);
    expect(css).toMatch(/\.panel\s*\{[^}]*box-shadow:\s*none/);
  });

  it("wires display face and mono numbers", () => {
    expect(css).toMatch(/--font-display:\s*var\(--font-fraunces\)/);
    expect(css).toMatch(/\.font-num/);
    expect(css).toMatch(/font-family:\s*var\(--font-mono\)/);
    const layout = read("app/layout.tsx");
    expect(layout).toMatch(/Fraunces/);
    expect(layout).toMatch(/--font-fraunces/);
  });

  it("M26 craft: tabular-nums, sticky matrix header, filename trunc, focus-visible", () => {
    expect(css).toMatch(/font-variant-numeric:\s*tabular-nums/);
    expect(css).toMatch(/\.coverage-table th[\s\S]*position:\s*sticky/);
    expect(css).toMatch(/\.filename-trunc/);
    expect(css).toMatch(/:focus-visible/);
    expect(css).toMatch(/line-clamp:\s*2|line-clamp-2/);
  });
});

describe("M23 brass discipline", () => {
  it("limits brass token uses outside About diagrams to sanctioned chrome", () => {
    const hits: string[] = [];
    const { readdirSync, readFileSync, statSync } = require("node:fs") as typeof import("node:fs");
    const { join } = require("node:path") as typeof import("node:path");
    function walk(dir: string) {
      for (const name of readdirSync(dir)) {
        const p = join(dir, name);
        if (name === "node_modules" || name === ".next") continue;
        if (statSync(p).isDirectory()) walk(p);
        else if (/\.(tsx|ts|css)$/.test(name)) {
          const text = readFileSync(p, "utf8");
          if (text.includes("--brass") || text.includes("var(--brass)")) {
            hits.push(p.replace(ROOT + "/", ""));
          }
        }
      }
    }
    walk(ROOT);
    // Allowed: globals, ScoreRing, recommendation winner CSS, sidebar active, about diagrams
    const allowed =
      /globals\.css|ScoreRing|about\/|Sidebar|recommendation|winner|score-ring|brand|theme\.tokens\.test/;
    const unexpected = hits.filter((h) => !allowed.test(h));
    expect(unexpected, `unexpected brass in ${unexpected.join(", ")}`).toEqual([]);
  });
});

describe("M23 no orphaned component hex", () => {
  it("has near-zero raw hex in components", () => {
    const { readdirSync, readFileSync, statSync } = require("node:fs") as typeof import("node:fs");
    const { join } = require("node:path") as typeof import("node:path");
    const found: string[] = [];
    function walk(dir: string) {
      for (const name of readdirSync(dir)) {
        const p = join(dir, name);
        if (statSync(p).isDirectory()) walk(p);
        else if (/\.(tsx|ts)$/.test(name)) {
          const text = readFileSync(p, "utf8");
          const matches = text.match(/#[0-9A-Fa-f]{6}/g) || [];
          for (const m of matches) found.push(`${p}:${m}`);
        }
      }
    }
    walk(join(ROOT, "components"));
    expect(found, found.join("\n")).toEqual([]);
  });
});
