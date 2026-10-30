const inr = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });

/** ₹ amounts in the Indian system: ₹8,42,310 / ₹12.4 L / ₹3.16 Cr. */
export function formatInr(value: number, compact = false): string {
  if (!compact) return `₹${inr.format(value)}`;
  const abs = Math.abs(value);
  if (abs >= 1e7) return `₹${(value / 1e7).toFixed(abs >= 1e8 ? 1 : 2)} Cr`;
  if (abs >= 1e5) return `₹${(value / 1e5).toFixed(1)} L`;
  if (abs >= 1e3) return `₹${(value / 1e3).toFixed(1)}K`;
  return `₹${inr.format(value)}`;
}

export function formatNumber(value: number, compact = false): string {
  if (compact && Math.abs(value) >= 1e5) return `${(value / 1e5).toFixed(1)} L`;
  return inr.format(value);
}

export function formatPct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}%`;
}

export function formatDate(iso: string, opts: Intl.DateTimeFormatOptions = {}): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    ...opts,
  });
}

/** Turn snake_case column names into labels. */
export function humanize(name: string): string {
  const s = name.replace(/_/g, " ").replace(/\bpct\b/, "%").replace(/\byoy\b/i, "YoY");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

const MONEY_HINTS = ["revenue", "cost", "sales", "price", "margin_inr", "at_risk", "fortnight"];

export function isMoneyColumn(name: string): boolean {
  const n = name.toLowerCase();
  return MONEY_HINTS.some((h) => n.includes(h)) && !n.includes("pct") && !n.includes("share");
}

export function formatCell(column: string, value: string | number | null): string {
  if (value === null) return "—";
  if (typeof value === "number") {
    if (isMoneyColumn(column)) return formatInr(value);
    if (column.toLowerCase().includes("pct")) return formatPct(value);
    return Number.isInteger(value) ? inr.format(value) : value.toLocaleString("en-IN");
  }
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return formatDate(value, { year: "numeric" });
  return value;
}
