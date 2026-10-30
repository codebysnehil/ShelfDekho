"use client";

import clsx from "clsx";
import { Check, ChevronDown } from "lucide-react";
import { type KeyboardEvent, useEffect, useId, useRef, useState } from "react";

export type SelectOption = { value: string; label: string; note?: string };

/**
 * The app's dropdown: looks like the rest of the product, and works like a native one. The
 * arrows move, Enter or Space chooses, Escape closes, typing a letter jumps to an option.
 */
export function Select({
  value,
  onChange,
  options,
  label,
  align = "left",
  className,
}: {
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  label: string;
  align?: "left" | "right";
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [cursor, setCursor] = useState(0);
  const root = useRef<HTMLDivElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const id = useId();
  const selected = options.find((o) => o.value === value) ?? options[0];

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  useEffect(() => {
    if (open) list.current?.children[cursor]?.scrollIntoView({ block: "nearest" });
  }, [open, cursor]);

  const show = () => {
    setCursor(Math.max(0, options.findIndex((o) => o.value === value)));
    setOpen(true);
  };
  const choose = (next: string) => {
    onChange(next);
    setOpen(false);
  };

  function onKeyDown(e: KeyboardEvent) {
    if (!open) {
      if (["ArrowDown", "ArrowUp", "Enter", " "].includes(e.key)) {
        e.preventDefault();
        show();
      }
      return;
    }
    if (e.key === "ArrowDown") setCursor((c) => Math.min(c + 1, options.length - 1));
    else if (e.key === "ArrowUp") setCursor((c) => Math.max(c - 1, 0));
    else if (e.key === "Home") setCursor(0);
    else if (e.key === "End") setCursor(options.length - 1);
    else if (e.key === "Enter" || e.key === " ") choose(options[cursor].value);
    else if (e.key === "Escape" || e.key === "Tab") {
      setOpen(false);
      if (e.key === "Tab") return;
    } else if (e.key.length === 1) {
      const hit = options.findIndex((o) => o.label.toLowerCase().startsWith(e.key.toLowerCase()));
      if (hit >= 0) setCursor(hit);
      return;
    } else return;
    e.preventDefault();
  }

  return (
    <div ref={root} className={clsx("relative min-w-0", className)}>
      <button
        type="button"
        role="combobox"
        aria-label={label}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={`${id}-list`}
        aria-activedescendant={open ? `${id}-${cursor}` : undefined}
        onClick={() => (open ? setOpen(false) : show())}
        onKeyDown={onKeyDown}
        className={clsx(
          "flex h-9 w-full items-center justify-between gap-2 rounded-md border bg-surface px-2.5 text-left text-sm transition-colors",
          open ? "border-ink" : "border-control hover:border-muted",
        )}
      >
        <span className="truncate">{selected?.label}</span>
        <ChevronDown
          className={clsx("size-4 flex-none text-muted transition-transform", open && "rotate-180")}
          strokeWidth={1.8}
          aria-hidden
        />
      </button>
      {open && (
        <ul
          ref={list}
          id={`${id}-list`}
          role="listbox"
          aria-label={label}
          className={clsx(
            "pop absolute top-full z-40 mt-1 max-h-80 w-max max-w-[300px] min-w-full overflow-auto rounded-lg border border-line bg-surface p-1 shadow-lg",
            align === "right" ? "right-0" : "left-0",
          )}
        >
          {options.map((o, i) => (
            <li
              key={o.value}
              id={`${id}-${i}`}
              role="option"
              aria-selected={o.value === value}
              onMouseEnter={() => setCursor(i)}
              onClick={() => choose(o.value)}
              className={clsx(
                "flex cursor-pointer items-center justify-between gap-4 rounded-md px-2.5 py-1.5 text-sm",
                i === cursor && "bg-active",
              )}
            >
              <span className="min-w-0">
                <span className={clsx("block truncate", o.value === value && "font-medium")}>{o.label}</span>
                {o.note && <span className="block truncate text-[13px] text-muted">{o.note}</span>}
              </span>
              {o.value === value && <Check className="size-4 flex-none" strokeWidth={2} aria-hidden />}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
