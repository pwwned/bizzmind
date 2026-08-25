"use client";
import { createContext, useContext } from "react";

export type Theme = "dark" | "light";

export function readTheme(): Theme {
  if (typeof document === "undefined") return "dark";
  const m = document.cookie.match(/(?:^|;\s*)theme=(dark|light)\b/);
  return (m?.[1] as Theme) ?? "dark";
}
export function writeTheme(t: Theme) {
  document.cookie = `theme=${t};path=/;max-age=31536000;SameSite=Lax`;
}
export const ThemeContext = createContext<{ theme: Theme; setTheme: (t: Theme) => void }>({ theme: "dark", setTheme: () => {} });
export const useTheme = () => useContext(ThemeContext);

export function ThemeToggle({ className = "" }: { className?: string }) {
  const { theme, setTheme } = useTheme();
  return (
    <button type="button" aria-label="theme" onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
      className={`inline-flex size-8 items-center justify-center rounded-lg border border-border text-muted-foreground hover:text-foreground ${className}`}>
      {theme === "dark" ? "☀" : "☾"}
    </button>
  );
}
