"use client";

import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { Settings2, SunMoon } from "lucide-react";

export type Theme = "light" | "dark" | "system";
type FontSize = "small" | "normal" | "large";
type LetterSpacing = "normal" | "wide";

type ThemeContextValue = {
  theme: Theme;
  fontSize: FontSize;
  letterSpacing: LetterSpacing;
  setTheme: (theme: Theme) => void;
  setFontSize: (fontSize: FontSize) => void;
  setLetterSpacing: (letterSpacing: LetterSpacing) => void;
  toggleTheme: () => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

function applyTheme(theme: Theme) {
  const resolvedTheme = theme === "system"
    ? window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"
    : theme;
  document.documentElement.dataset.theme = resolvedTheme;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(() => {
    if (typeof window === "undefined") return "light";
    const saved = localStorage.getItem("nexaiq-theme");
    return saved === "dark" || saved === "system" ? saved : "light";
  });
  const [fontSize, setFontSize] = useState<FontSize>(() => {
    if (typeof window === "undefined") return "normal";
    const saved = localStorage.getItem("enterprise-ai-font-size");
    return saved === "small" || saved === "large" ? saved : "normal";
  });
  const [letterSpacing, setLetterSpacing] = useState<LetterSpacing>(() => {
    if (typeof window === "undefined") return "normal";
    return localStorage.getItem("enterprise-ai-letter-spacing") === "wide" ? "wide" : "normal";
  });

  useEffect(() => {
    applyTheme(theme);
    localStorage.setItem("nexaiq-theme", theme);
    document.documentElement.style.setProperty(
      "--app-font-scale",
      fontSize === "small" ? "0.9" : fontSize === "large" ? "1.1" : "1",
    );
    document.documentElement.style.setProperty(
      "--app-letter-spacing",
      letterSpacing === "wide" ? "0.03em" : "0",
    );
    localStorage.setItem("enterprise-ai-font-size", fontSize);
    localStorage.setItem("enterprise-ai-letter-spacing", letterSpacing);
    if (theme !== "system") return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const updateSystemTheme = () => applyTheme("system");
    media.addEventListener("change", updateSystemTheme);
    return () => media.removeEventListener("change", updateSystemTheme);
  }, [theme, fontSize, letterSpacing]);

  function toggleTheme() {
    setTheme(theme === "light" ? "dark" : theme === "dark" ? "system" : "light");
  }

  return <ThemeContext.Provider value={{ theme, fontSize, letterSpacing, setTheme, setFontSize, setLetterSpacing, toggleTheme }}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const value = useContext(ThemeContext);
  if (!value) throw new Error("useTheme must be used inside ThemeProvider.");
  return value;
}

export function ThemeToggle({ className = "icon-button" }: { className?: string }) {
  const { toggleTheme } = useTheme();
  return (
    <button
      type="button"
      className={className}
      onClick={toggleTheme}
      aria-label="Cycle light, dark, and system theme"
      title="Cycle light, dark, and system theme"
      data-testid="theme-toggle"
    >
      <SunMoon size={18} />
    </button>
  );
}

export function AppearanceMenu({ className = "icon-button" }: { className?: string }) {
  const { theme, fontSize, letterSpacing, setTheme, setFontSize, setLetterSpacing } = useTheme();
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function dismiss(event: PointerEvent) {
      if (event.target instanceof Node && !menuRef.current?.contains(event.target)) setOpen(false);
    }
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("pointerdown", dismiss);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", dismiss);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  return (
    <div className="appearance-menu" ref={menuRef}>
      <button
        type="button"
        className={className}
        aria-label="Appearance settings"
        aria-haspopup="dialog"
        aria-expanded={open}
        title="Appearance settings"
        data-testid="appearance-menu-toggle"
        onClick={() => setOpen((value) => !value)}
      >
        <Settings2 size={18} />
      </button>
      {open ? (
        <section className="appearance-popover" role="dialog" aria-label="Appearance settings">
          <h2>Appearance</h2>
          <AppearanceSetting label="Theme" options={["Light", "Dark", "System"]} value={theme} onChange={(value) => setTheme(value.toLowerCase() as Theme)} testId="theme" />
          <AppearanceSetting label="Text size" options={["Small", "Normal", "Large"]} value={fontSize} onChange={(value) => setFontSize(value.toLowerCase() as FontSize)} testId="font-size" />
          <AppearanceSetting label="Letter spacing" options={["Normal", "Wide"]} value={letterSpacing} onChange={(value) => setLetterSpacing(value.toLowerCase() as LetterSpacing)} testId="letter-spacing" />
        </section>
      ) : null}
    </div>
  );
}

function AppearanceSetting<T extends string>({ label, options, value, onChange, testId }: {
  label: string;
  options: string[];
  value: T;
  onChange: (value: string) => void;
  testId: string;
}) {
  return (
    <fieldset className="appearance-setting">
      <legend>{label}</legend>
      <div className="appearance-options">
        {options.map((option) => {
          const optionValue = option.toLowerCase();
          return (
            <button
              key={option}
              type="button"
              aria-pressed={value === optionValue}
              className={value === optionValue ? "appearance-option appearance-option-active" : "appearance-option"}
              data-testid={`${testId}-${optionValue}`}
              onClick={() => onChange(optionValue)}
            >
              {option}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}