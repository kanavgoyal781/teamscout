"use client";

import { Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";

import { applyThemeClass, resolveInitialTheme, writeThemeCookie, type ThemeMode } from "../../lib/theme";

export default function ThemeToggle() {
  const [mode, setMode] = useState<ThemeMode>("dark");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const initial = resolveInitialTheme();
    setMode(initial);
    applyThemeClass(initial);
    setMounted(true);
  }, []);

  function toggle() {
    const next: ThemeMode = mode === "dark" ? "light" : "dark";
    setMode(next);
    applyThemeClass(next);
    writeThemeCookie(next);
  }

  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={toggle}
      aria-label={mode === "dark" ? "Switch to light mode" : "Switch to dark mode"}
      title={mode === "dark" ? "Light mode" : "Dark mode"}
    >
      {mounted && mode === "dark" ? <Sun size={16} /> : <Moon size={16} />}
    </button>
  );
}
