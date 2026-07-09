/** Theme helpers — cookie only (no browser storage APIs). */

export type ThemeMode = "dark" | "light";

export const THEME_COOKIE = "teamscout-theme";

export function readThemeCookie(): ThemeMode | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(/(?:^|; )teamscout-theme=(dark|light)/);
  return match ? (match[1] as ThemeMode) : null;
}

export function writeThemeCookie(mode: ThemeMode): void {
  // 1 year; path=/ so layout script + client share it
  document.cookie = `${THEME_COOKIE}=${mode}; path=/; max-age=31536000; SameSite=Lax`;
}

export function applyThemeClass(mode: ThemeMode): void {
  const root = document.documentElement;
  root.classList.toggle("dark", mode === "dark");
  root.classList.toggle("light", mode === "light");
  root.dataset.theme = mode;
}

export function resolveInitialTheme(): ThemeMode {
  const stored = readThemeCookie();
  if (stored) return stored;
  // Dark-mode-first: only flip to light if user preference is light
  if (typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: light)").matches) {
    return "light";
  }
  return "dark";
}
