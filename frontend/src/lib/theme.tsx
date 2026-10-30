"use client";

import clsx from "clsx";
import { Monitor, Moon, Sun } from "lucide-react";
import { useEffect, useSyncExternalStore } from "react";

export type ThemeChoice = "light" | "dark" | "system";

const KEY = "shelfiq.theme";
const EVENT = "shelfiq-theme";

/** Runs before first paint (see layout.tsx), so a dark-mode visitor never sees a white flash. */
export const THEME_SCRIPT = `try{var c=localStorage.getItem("${KEY}");var d=c==="dark"||(c!=="light"&&matchMedia("(prefers-color-scheme: dark)").matches);document.documentElement.dataset.theme=d?"dark":"light"}catch(e){document.documentElement.dataset.theme="light"}`;

function readChoice(): ThemeChoice {
  try {
    const stored = localStorage.getItem(KEY);
    return stored === "light" || stored === "dark" ? stored : "system";
  } catch {
    return "system";
  }
}

function apply(choice: ThemeChoice) {
  const dark =
    choice === "dark" ||
    (choice === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
}

function setChoice(choice: ThemeChoice) {
  try {
    if (choice === "system") localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, choice);
  } catch {}
  apply(choice);
  window.dispatchEvent(new Event(EVENT));
}

function subscribe(listener: () => void) {
  window.addEventListener(EVENT, listener);
  window.addEventListener("storage", listener);
  return () => {
    window.removeEventListener(EVENT, listener);
    window.removeEventListener("storage", listener);
  };
}

function useThemeChoice(): ThemeChoice {
  const choice = useSyncExternalStore(subscribe, readChoice, () => "system" as ThemeChoice);
  // On "system", follow the device when it changes, for example at sunset.
  useEffect(() => {
    if (choice !== "system") return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => apply("system");
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [choice]);
  return choice;
}

const OPTIONS = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: Monitor },
] as const;

/** The appearance setting: three explicit choices. */
export function ThemeSwitch({ className }: { className?: string }) {
  const choice = useThemeChoice();
  return (
    <div
      role="radiogroup"
      aria-label="Appearance"
      className={clsx("inline-grid grid-cols-3 rounded-md bg-raised p-0.5", className)}
    >
      {OPTIONS.map(({ value, label, icon: Icon }) => (
        <button
          key={value}
          role="radio"
          aria-checked={choice === value}
          aria-label={label}
          title={label}
          onClick={() => setChoice(value)}
          className={clsx(
            "flex h-7 items-center justify-center rounded transition-colors",
            choice === value ? "bg-surface text-ink" : "text-muted hover:text-ink",
          )}
        >
          <Icon className="size-3.5" strokeWidth={1.8} aria-hidden />
        </button>
      ))}
    </div>
  );
}

/** One button that steps through the choices, for tight bars. */
export function ThemeCycle({ className }: { className?: string }) {
  const choice = useThemeChoice();
  const index = OPTIONS.findIndex((o) => o.value === choice);
  const { icon: Icon, label } = OPTIONS[index];
  const next = OPTIONS[(index + 1) % OPTIONS.length];
  return (
    <button
      onClick={() => setChoice(next.value)}
      aria-label={`Appearance: ${label}. Switch to ${next.label}.`}
      title={`Appearance: ${label}`}
      className={clsx("flex size-9 flex-none items-center justify-center rounded-md transition-colors", className)}
    >
      <Icon className="size-4" strokeWidth={1.8} aria-hidden />
    </button>
  );
}
