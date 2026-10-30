"use client";

import clsx from "clsx";
import { ChevronDown } from "lucide-react";
import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";

/** A white panel on the stone ground: a 1px whisper border, no shadow, 8px corners. */
export function Panel({
  title,
  meta,
  action,
  children,
  className,
  bodyClassName,
}: {
  title?: ReactNode;
  meta?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={clsx("rounded-lg border border-line bg-surface", className)}>
      {(title || action) && (
        <header className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 px-5 pt-4">
          <div className="flex min-w-0 flex-wrap items-baseline gap-x-2">
            {title && <h2 className="text-[15px] font-semibold">{title}</h2>}
            {meta && <span className="text-sm text-muted">{meta}</span>}
          </div>
          {action}
        </header>
      )}
      <div className={clsx("px-5 pt-3 pb-5", bodyClassName)}>{children}</div>
    </section>
  );
}

/** Detail kept out of the way: one line says what it holds and its finding. */
export function Disclosure({
  title,
  summary,
  children,
}: {
  title: string;
  summary?: ReactNode;
  children: ReactNode;
}) {
  return (
    <details className="group rounded-lg border border-line bg-surface">
      <summary className="flex cursor-pointer list-none flex-wrap items-baseline gap-x-3 gap-y-0.5 px-5 py-3.5 transition-colors hover:bg-hover [&::-webkit-details-marker]:hidden">
        <span className="font-semibold">{title}</span>
        {summary && <span className="min-w-0 flex-1 basis-60 text-sm text-muted">{summary}</span>}
        <ChevronDown
          className="ml-auto size-4 flex-none self-center text-muted transition-transform group-open:rotate-180"
          aria-hidden
        />
      </summary>
      <div className="overflow-x-auto px-5 pt-1 pb-5">{children}</div>
    </details>
  );
}

/** Loading placeholder at the real size of what it stands for; flat, no shimmer. */
export function Bar({ className }: { className?: string }) {
  return <span className={clsx("block rounded bg-raised", className)} aria-hidden />;
}

export function BlockError({ onRetry }: { message?: string; onRetry?: () => void }) {
  return (
    <p className="text-sm text-ink">
      Couldn&apos;t load this just now.{" "}
      {onRetry && (
        <button onClick={onRetry} className="font-medium underline underline-offset-2">
          Retry
        </button>
      )}
    </p>
  );
}

export function Segmented<T extends string | number>({
  value,
  options,
  onChange,
  label,
  small,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
  label: string;
  small?: boolean;
}) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className={clsx(
        "inline-flex items-center rounded-md bg-raised p-0.5",
        small ? "h-7" : "h-9",
      )}
    >
      {options.map((o) => (
        <button
          key={String(o.value)}
          role="radio"
          aria-checked={o.value === value}
          onClick={() => onChange(o.value)}
          className={clsx(
            "h-full rounded text-sm transition-colors",
            small ? "px-2" : "px-3",
            o.value === value
              ? "bg-surface font-medium text-ink shadow-[0_1px_2px_rgba(15,28,28,0.08)]"
              : "text-muted hover:text-ink",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

const buttonStyles = {
  primary: "bg-primary text-primary-ink hover:bg-primary-hover",
  secondary: "bg-raised text-ink hover:bg-raised-hover",
} as const;

export function Button({
  variant = "secondary",
  className,
  ...props
}: ComponentProps<"button"> & { variant?: keyof typeof buttonStyles }) {
  return (
    <button
      {...props}
      className={clsx(
        "inline-flex h-9 items-center gap-1.5 rounded-md px-3.5 text-sm font-medium transition-colors active:translate-y-px disabled:opacity-60",
        buttonStyles[variant],
        className,
      )}
    />
  );
}

export function ButtonLink({
  variant = "secondary",
  className,
  ...props
}: ComponentProps<typeof Link> & { variant?: keyof typeof buttonStyles }) {
  return (
    <Link
      {...props}
      className={clsx(
        "inline-flex h-9 items-center gap-1.5 rounded-md px-3.5 text-sm font-medium transition-colors",
        buttonStyles[variant],
        className,
      )}
    />
  );
}

/** A pale pill with dark text of the same hue, for status inside rows. */
export function Pill({
  tone,
  children,
}: {
  tone: "negative" | "positive" | "neutral";
  children: ReactNode;
}) {
  return (
    <span
      className={clsx(
        "inline-flex h-5 flex-none items-center rounded px-1.5 text-xs font-medium whitespace-nowrap",
        tone === "negative" && "bg-pill-negative-bg text-pill-negative-ink",
        tone === "positive" && "bg-pill-positive-bg text-pill-positive-ink",
        tone === "neutral" && "bg-pill-neutral-bg text-pill-neutral-ink",
      )}
    >
      {children}
    </span>
  );
}

/**
 * A change against a named baseline. Colour says good or bad, not up or down, and only
 * when the change is large enough to matter; small or missing changes stay grey.
 */
export function Change({
  value,
  unit = "%",
  goodWhen = "up",
  baseline,
  threshold = 0.5,
  className,
}: {
  value: number | null | undefined;
  unit?: "%" | " pts";
  goodWhen?: "up" | "down";
  baseline?: string;
  threshold?: number;
  className?: string;
}) {
  if (value === null || value === undefined) {
    return <span className={clsx("text-muted", className)}>—</span>;
  }
  const good = goodWhen === "up" ? value > 0 : value < 0;
  const matters = Math.abs(value) >= threshold;
  return (
    <span className={clsx("num", className)}>
      <span
        className={clsx(
          !matters ? "text-muted" : good ? "text-positive" : "text-negative",
        )}
      >
        {value > 0 ? "+" : value < 0 ? "−" : ""}
        {Math.abs(value).toFixed(1)}
        {unit}
      </span>
      {baseline && <span className="text-muted"> {baseline}</span>}
    </span>
  );
}

/**
 * ShelfIQ's own element: days of stock cover drawn against the reorder lead time.
 * The tick is the lead time; the bar turns red only when the shelf empties before a
 * reorder placed today could arrive.
 */
export function CoverBar({
  cover,
  leadTime,
  scaleDays = 28,
}: {
  cover: number | null;
  leadTime: number;
  scaleDays?: number;
}) {
  const atRisk = cover !== null && cover < leadTime;
  const filled = cover === null ? 100 : Math.min(cover / scaleDays, 1) * 100;
  const tick = Math.min(leadTime / scaleDays, 1) * 100;
  return (
    <span
      className="relative block h-2 w-full rounded-full bg-raised"
      role="img"
      aria-label={`${cover === null ? "No demand" : `${cover.toFixed(1)} days of cover`} against a ${leadTime}-day lead time`}
    >
      <span
        className={clsx("absolute inset-y-0 left-0 rounded-full", atRisk ? "bg-negative" : "bg-hue")}
        style={{ width: `${filled}%` }}
      />
      <span className="absolute -top-1 -bottom-1 w-0.5 rounded-full bg-ink" style={{ left: `${tick}%` }} />
    </span>
  );
}
