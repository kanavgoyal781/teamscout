"use client";

import { Moon, Sun } from "lucide-react";
import { useSyncExternalStore } from "react";

import { applyThemeClass, resolveInitialTheme, writeThemeCookie, type ThemeMode } from "../../lib/theme";

/** Minimal external store so theme can hydrate from cookie without setState-in-effect. */
let themeSnapshot: ThemeMode | null = null;
const themeListeners = new Set<() => void>();

/** Pure snapshot — no mutation. Cache is filled in subscribe / commit only. */
function getThemeSnapshot(): ThemeMode {
  return themeSnapshot ?? resolveInitialTheme();
}

function getServerThemeSnapshot(): ThemeMode {
  // SSR default matches light-first product; client hydrate uses cookie.
  return "light";
}

function ensureThemeStore(): void {
  if (themeSnapshot == null) {
    themeSnapshot = resolveInitialTheme();
    // Keep class in sync after React hydrates font variables on <html>
    applyThemeClass(themeSnapshot);
  }
}

function subscribeTheme(onStoreChange: () => void): () => void {
  ensureThemeStore();
  themeListeners.add(onStoreChange);
  return () => {
    themeListeners.delete(onStoreChange);
  };
}

function commitTheme(next: ThemeMode): void {
  themeSnapshot = next;
  applyThemeClass(next);
  writeThemeCookie(next);
  themeListeners.forEach((listener) => listener());
}

export default function ThemeToggle() {
  const mode = useSyncExternalStore(subscribeTheme, getThemeSnapshot, getServerThemeSnapshot);

  function toggle() {
    commitTheme(mode === "dark" ? "light" : "dark");
  }

  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={toggle}
      aria-label={mode === "dark" ? "Switch to light mode" : "Switch to dark mode"}
      title={mode === "dark" ? "Light mode" : "Dark mode"}
      suppressHydrationWarning
    >
      {mode === "dark" ? <Sun size={16} /> : <Moon size={16} />}
    </button>
  );
}
