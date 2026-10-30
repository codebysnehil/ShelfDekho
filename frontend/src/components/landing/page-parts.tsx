"use client";

import clsx from "clsx";
import { ArrowRight, BarChart3, Loader2, Package, Sparkles } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { MovedBars, SalesTable, signedInr } from "@/components/analysis";
import { LegendItem, MetricChart, ResultChart } from "@/components/charts";
import { ShelfMark } from "@/components/mark";
import { StockRunway } from "@/components/stock-runway";
import { Change, CoverBar } from "@/components/ui";
import { useServerReady, WakeBanner } from "@/components/wake-banner";
import type { AlertRow, Kpi } from "@/lib/api";
import { demoLogin } from "@/lib/api";
import { formatCell, formatDate, formatInr, formatNumber, humanize } from "@/lib/format";
import { snapshot, suggestedOrder } from "@/lib/snapshot";
import { ThemeCycle } from "@/lib/theme";
import { Rise } from "./motion";

const { shelves, accuracy, answers, summary, trend } = snapshot;

const H2 = "text-[30px] leading-[1.08] font-bold tracking-[-0.03em] md:text-[clamp(40px,3.9vw,60px)]";
const LEAD = "text-[20px] leading-[1.4]";
const SECTION = "scroll-mt-4 px-4 py-20 md:px-8 md:py-28";

/** Opens the demo. A slow first start gets a plain explanation instead of a hang. */
function useStartDemo() {
  const router = useRouter();
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function start(href = "/dashboard") {
    setStarting(true);
    setError(null);
    try {
      await demoLogin();
      router.push(href);
    } catch {
      setError("Still getting things ready. Give it a few seconds and try again.");
      setStarting(false);
    }
  }
  return { start, starting, error };
}

function DemoButton({ className }: { className?: string }) {
  const { start, starting, error } = useStartDemo();
  return (
    <div className={className}>
      <button
        onClick={() => start()}
        disabled={starting}
        className="inline-flex h-12 items-center gap-2 bg-white px-6 text-[16px] font-medium text-[#141414] transition-transform hover:-translate-y-0.5 active:translate-y-0 disabled:opacity-70"
      >
        {starting ? <Loader2 className="size-4 animate-spin" aria-hidden /> : null}
        Open the live demo
        <ArrowRight className="size-4" aria-hidden />
      </button>
      {error && <p className="mt-2 text-[16px] text-white">{error}</p>}
    </div>
  );
}

const key = (r: AlertRow) => `${r.store_id}-${r.product_id}`;
const worst = [...shelves.rows]
  .filter((r) => r.status === "stockout_risk")
  .sort((a, b) => b.revenue_at_risk - a.revenue_at_risk);

function describe(r: AlertRow) {
  const cover = r.days_of_cover;
  if (r.status === "stockout_risk") {
    return `${r.on_hand} left, selling ${r.daily_demand.toFixed(1)} a day. Empty in ${cover?.toFixed(1)} days; a reorder takes ${r.lead_time_days}.`;
  }
  if (r.status === "overstock") {
    return cover === null
      ? `${r.on_hand} on the shelf and no expected sales.`
      : `${Math.round(cover)} days of stock on the shelf. Too much money is tied up here.`;
  }
  return `${Math.round(cover ?? 0)} days of stock, comfortably past the ${r.lead_time_days}-day reorder time.`;
}

function Hero() {
  const server = useServerReady();
  return (
    <section className="relative isolate overflow-hidden bg-field pb-[30svh] text-white md:pb-[34svh]">
      <Image
        src="/photos/kirana-shop.jpg"
        alt="A kirana store: sacks of basmati rice stacked behind the glass, crates on the pavement"
        fill
        priority
        sizes="100vw"
        className="drift -z-20 object-cover object-[58%_100%]"
      />
      <div className="absolute inset-0 -z-10 bg-black/60" aria-hidden />

      <header className="flex items-center justify-between gap-3 px-4 pt-4 md:px-8 md:pt-5">
        <Link href="/" className="flex items-center gap-2 text-[20px] font-semibold tracking-[-0.01em]">
          <ShelfMark size={24} /> ShelfIQ
        </Link>
        <nav className="flex items-center gap-1 text-[16px] sm:gap-5">
          <a href="#shelves" className="hidden hover:underline sm:inline">
            Stock
          </a>
          <a href="#sales" className="hidden hover:underline sm:inline">
            Sales
          </a>
          <a href="#ask" className="hidden hover:underline sm:inline">
            Ask
          </a>
          <ThemeCycle className="text-white/85 hover:text-white" />
        </nav>
      </header>

      <div className="px-4 pt-[9svh] md:px-8 md:pt-[11svh]">
        <h1 className="text-[9vw] leading-[1.02] font-bold tracking-[-0.035em] md:text-[clamp(56px,6.4vw,104px)]">
          Know what runs out
          <br />
          before it does.
        </h1>
        <p className={clsx(LEAD, "mt-6 max-w-[52ch]")}>
          ShelfIQ tells a grocery chain what sold, what will sell and what to reorder today, in every store, before the
          shelf is empty.
        </p>
        <DemoButton className="mt-7" />
        {server.slow && (
          <div className="mt-3 max-w-[60ch] text-ink">
            <WakeBanner show />
          </div>
        )}
      </div>
    </section>
  );
}

function kpiValue(k: Kpi) {
  if (k.unit === "inr") return formatInr(k.value, true);
  if (k.unit === "pct") return `${k.value.toFixed(1)}%`;
  return formatNumber(k.value, true);
}

/** The real Overview screen, drawn from real figures and rising out of the hero. */
function ProductWindow() {
  const nav = [
    { label: "Overview", icon: BarChart3, active: true, badge: 0 },
    { label: "Stock", icon: Package, active: false, badge: shelves.counts.stockout_risk },
    { label: "Analyst", icon: Sparkles, active: false, badge: 0 },
  ];
  return (
    <div className="relative z-10 -mt-[24svh] px-4 md:-mt-[28svh] md:px-8">
      <div
        data-ui
        className="mx-auto grid max-w-[1320px] overflow-hidden rounded-xl border border-line bg-ground text-ink shadow-2xl md:grid-cols-[190px_minmax(0,1fr)]"
      >
        <aside className="hidden flex-col gap-1 border-r border-line p-3 text-[13px] md:flex">
          <p className="mb-3 flex items-center gap-2 px-1 text-[16px] font-semibold">
            <ShelfMark size={18} /> ShelfIQ
          </p>
          {nav.map(({ label, icon: Icon, active, badge }) => (
            <span
              key={label}
              className={clsx("flex h-8 items-center gap-2 rounded-md px-2", active ? "bg-active font-medium" : "text-muted")}
            >
              <Icon className="size-4" strokeWidth={1.7} aria-hidden />
              {label}
              {badge ? (
                <span className="num ml-auto rounded bg-pill-negative-bg px-1.5 text-xs font-medium text-pill-negative-ink">
                  {badge}
                </span>
              ) : null}
            </span>
          ))}
        </aside>
        <div className="min-w-0 p-4 md:p-5">
          <p className="text-[20px] font-semibold tracking-[-0.01em]">Overview</p>
          <div className="mt-3 grid grid-cols-2 rounded-lg border border-line bg-surface lg:grid-cols-4">
            {summary.kpis.map((k, i) => (
              <div
                key={k.key}
                className={clsx(
                  "p-3",
                  i % 2 === 1 && "border-l border-line",
                  i === 2 && "lg:border-l",
                  i > 1 && "border-t border-line lg:border-t-0",
                )}
              >
                <p className="text-[13px] text-muted">{k.label}</p>
                <p className={clsx("num text-[22px] leading-8", k.key === "revenue" ? "font-bold" : "font-medium")}>
                  {kpiValue(k)}
                </p>
                <p className="text-[13px]">
                  <Change
                    value={k.change_pct}
                    unit={k.unit === "pct" ? " pts" : "%"}
                    threshold={k.key === "promo_share" ? Infinity : 0.5}
                  />
                </p>
              </div>
            ))}
          </div>
          <div className="mt-3 grid gap-3 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
            <div className="min-w-0 rounded-lg border border-line bg-surface p-4">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <p className="text-[13px] font-medium">Revenue by week</p>
                <div className="flex gap-3">
                  <LegendItem label="This year" kind="line" color="var(--hue)" />
                  <LegendItem label="Last year" kind="line" color="var(--comparison)" />
                </div>
              </div>
              <MetricChart trend={trend} height={250} />
            </div>
            <div className="rounded-lg border border-line bg-surface p-4">
              <p className="mb-2 text-[13px] font-medium">Runs out before restock</p>
              <ul>
                {worst.slice(0, 5).map((r) => (
                  <li
                    key={key(r)}
                    className="grid grid-cols-[minmax(0,1fr)_72px_52px] items-center gap-2 border-t border-rule py-1.5 text-[13px]"
                  >
                    <span className="min-w-0">
                      <span className="block truncate">{r.product_name}</span>
                      <span className="block truncate text-muted">{r.store_name.split(",")[0]}</span>
                    </span>
                    <CoverBar cover={r.days_of_cover} leadTime={r.lead_time_days} />
                    <span className="num text-right">{formatInr(r.revenue_at_risk, true)}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/** Three questions, answered further down the page. */
function Questions() {
  const items = [
    [
      "#shelves",
      "What is about to run out?",
      `${shelves.counts.stockout_risk} shelves, ${formatInr(shelves.revenue_at_risk, true)} of sales at risk.`,
    ],
    ["#sales", "Why did sales move?", "The real reason, ahead of the headline number."],
    ["#ask", "Why that store? Why that product?", "Ask in your own words and get the numbers back."],
  ];
  return (
    <section aria-labelledby="questions-title" className="px-4 pt-20 pb-4 md:px-8 md:pt-28">
      <Rise>
        <h2 id="questions-title" className={H2}>
          Three questions every morning
        </h2>
      </Rise>
      <div className="mt-10 grid gap-3 md:grid-cols-3">
        {items.map(([href, q, a]) => (
          <Rise key={href}>
            <a href={href} className="group block h-full bg-surface p-6 transition-colors hover:bg-hover">
              <span className="block text-[20px] leading-snug font-medium">{q}</span>
              <span className="mt-2 block text-[16px] leading-[1.5] text-muted">{a}</span>
              <ArrowRight className="mt-4 size-5 transition-transform group-hover:translate-x-1" aria-hidden />
            </a>
          </Rise>
        ))}
      </div>
    </section>
  );
}

/** Every shelf in the chain as one square, in real data. Red empties before a reorder lands. */
function ShelfWall({ selected, onSelect }: { selected: AlertRow; onSelect: (r: AlertRow) => void }) {
  const rows = useMemo(
    () => [...shelves.rows].sort((a, b) => a.store_id - b.store_id || a.product_id - b.product_id),
    [],
  );
  const { stockout_risk: risk, healthy, overstock } = shelves.counts;
  return (
    <div className="bg-field p-4 text-white md:p-6">
      <div
        data-ui
        className="grid grid-cols-[repeat(24,minmax(0,1fr))] gap-0.5 md:grid-cols-[repeat(48,minmax(0,1fr))]"
        role="group"
        aria-label={`${rows.length} shelves: ${risk} run out before restock, ${healthy} healthy, ${overstock} overstocked`}
      >
        {rows.map((r) => {
          const isRisk = r.status === "stockout_risk";
          return (
            <button
              key={key(r)}
              // Only the shelves that need attention are tab stops, or the wall traps the keyboard.
              tabIndex={isRisk ? 0 : -1}
              aria-label={`${r.product_name}, ${r.store_name}: ${describe(r)}`}
              onMouseEnter={() => onSelect(r)}
              onFocus={() => onSelect(r)}
              onClick={() => onSelect(r)}
              className={clsx(
                "aspect-square rounded-[2px]",
                isRisk ? "bg-[#e5484d]" : r.status === "overstock" ? "bg-[#8f8e88]" : "bg-[#343432]",
                key(r) === key(selected) && "outline-2 outline-offset-1 outline-white",
              )}
            />
          );
        })}
      </div>
      <div className="mt-3 grid gap-x-8 gap-y-1 md:grid-cols-[minmax(0,1fr)_auto] md:items-baseline">
        <p className="min-h-[3em] text-[16px] leading-[1.5] md:min-h-0" aria-live="polite">
          <span className="font-medium">
            {selected.product_name}, {selected.store_name.split(",")[0]}.
          </span>{" "}
          <span className="text-white/80">{describe(selected)}</span>
        </p>
        <p className="num flex flex-wrap gap-x-4 text-[13px] text-white/80">
          <span className="inline-flex items-center gap-1.5">
            <span className="size-2.5 rounded-[2px] bg-[#e5484d]" /> {risk} run out
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="size-2.5 rounded-[2px] bg-[#343432] outline-1 outline-white/25" /> {healthy} healthy
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="size-2.5 rounded-[2px] bg-[#8f8e88]" /> {overstock} overstocked
          </span>
        </p>
      </div>
    </div>
  );
}

function Shelves({ selected, onSelect }: { selected: AlertRow; onSelect: (r: AlertRow) => void }) {
  const [safety, setSafety] = useState(snapshot.safety_days);
  const [caseSize, setCaseSize] = useState(1);
  const units = suggestedOrder(selected, safety, caseSize);
  return (
    <section id="shelves" aria-labelledby="shelves-title" className={SECTION}>
      <div className="grid gap-x-10 gap-y-4 lg:grid-cols-2 lg:items-end">
        <Rise>
          <h2 id="shelves-title" className={H2}>
            Every shelf in the chain, at one look
          </h2>
        </Rise>
        <Rise>
          <p className={clsx(LEAD, "max-w-[52ch]")}>
            Each square is one product in one store. Red means it will be empty before a reorder can arrive. Point at
            any of them.
          </p>
        </Rise>
      </div>

      <Rise className="mt-10">
        <ShelfWall selected={selected} onSelect={onSelect} />
      </Rise>

      <div className="mt-16 grid gap-x-10 gap-y-4 lg:grid-cols-2 lg:items-end">
        <Rise>
          <h3 className={H2}>Then order the right amount</h3>
        </Rise>
        <Rise>
          <p className={clsx(LEAD, "max-w-[52ch]")}>
            See the day it empties and the day a delivery lands. Set your own safety stock and supplier case size, and
            the order works itself out.
          </p>
        </Rise>
      </div>

      <div className="mt-10 grid gap-3 lg:grid-cols-2">
        <Rise>
          <ul data-ui className="h-full rounded-lg border border-line bg-surface p-1.5">
            {worst.slice(0, 7).map((r) => (
              <li key={key(r)}>
                <button
                  onClick={() => onSelect(r)}
                  aria-pressed={key(r) === key(selected)}
                  className={clsx(
                    "grid w-full grid-cols-[minmax(0,1fr)_84px_64px] items-center gap-3 rounded-md px-3 py-2.5 text-left transition-colors sm:grid-cols-[minmax(0,1fr)_120px_72px]",
                    key(r) === key(selected) ? "bg-active" : "hover:bg-hover",
                  )}
                >
                  <span className="min-w-0">
                    <span className="block truncate text-[16px]">{r.product_name}</span>
                    <span className="block truncate text-[13px] text-muted">{r.store_name}</span>
                  </span>
                  <span>
                    <CoverBar cover={r.days_of_cover} leadTime={r.lead_time_days} />
                    <span className="num mt-1 block text-[13px] text-muted">
                      {r.days_of_cover?.toFixed(1)} of {r.lead_time_days} days
                    </span>
                  </span>
                  <span className="num text-right text-[16px]">{formatInr(r.revenue_at_risk, true)}</span>
                </button>
              </li>
            ))}
          </ul>
        </Rise>

        <Rise>
          <div data-ui className="h-full rounded-lg border border-line bg-surface p-6">
            <p className="text-[20px] font-medium">{selected.product_name}</p>
            <p className="mb-4 text-[13px] text-muted">{selected.store_name}</p>
            <StockRunway
              asOf={snapshot.as_of}
              onHand={selected.on_hand}
              dailyDemand={selected.daily_demand}
              leadTime={selected.lead_time_days}
              order={units}
            />
            <div className="mt-5 grid gap-4 sm:grid-cols-2">
              <label className="block text-[13px]">
                <span className="flex justify-between">
                  <span className="text-muted">Safety stock</span>
                  <span className="num">{safety} days</span>
                </span>
                <input
                  type="range"
                  min={0}
                  max={28}
                  value={safety}
                  onChange={(e) => setSafety(Number(e.target.value))}
                  className="mt-1 h-8 w-full accent-[var(--hue)]"
                />
              </label>
              <div className="text-[13px]">
                <p className="text-muted">Supplier case size</p>
                <div role="radiogroup" aria-label="Supplier case size" className="mt-1 inline-flex rounded-md bg-raised p-0.5">
                  {[1, 6, 12, 24].map((c) => (
                    <button
                      key={c}
                      role="radio"
                      aria-checked={c === caseSize}
                      onClick={() => setCaseSize(c)}
                      className={clsx(
                        "h-8 rounded px-3 transition-colors",
                        c === caseSize ? "bg-surface font-medium" : "text-muted hover:text-ink",
                      )}
                    >
                      {c === 1 ? "Units" : c}
                    </button>
                  ))}
                </div>
              </div>
            </div>
            <div className="mt-5 flex items-end justify-between bg-active px-4 py-3">
              <div>
                <p className="text-[13px] text-muted">Order today</p>
                <p className="num text-[30px] leading-9 font-bold">{units.toLocaleString("en-IN")} units</p>
              </div>
              <p className="num text-[16px]">{formatInr(units * selected.unit_price)}</p>
            </div>
          </div>
        </Rise>
      </div>
    </section>
  );
}

/** The finding set as the headline, with the evidence under it. */
function Sales() {
  const { by_category, matrix } = snapshot;
  const revenue = summary.kpis.find((k) => k.key === "revenue")!;
  const rest = by_category.rows.filter((r) => r.name !== "Festive & Gifting" && r.revenue_ly);
  const now = rest.reduce((sum, r) => sum + r.revenue, 0);
  const before = rest.reduce((sum, r) => sum + (r.revenue_ly ?? 0), 0);
  const without = ((now - before) / before) * 100;
  const change = revenue.change_pct ?? 0;
  const word = (v: number) => (v >= 0 ? "Up" : "Down");
  const moved = by_category.rows
    .map((r) => ({ name: r.name, delta: r.revenue - (r.revenue_ly ?? 0) }))
    .sort((a, b) => b.delta - a.delta);
  const total = moved.reduce((sum, r) => sum + r.delta, 0);
  const festival = summary.insights.find((i) => i.kind === "festival");
  return (
    <section id="sales" aria-labelledby="sales-title" className={clsx(SECTION, "bg-surface")}>
      <div className="grid gap-x-10 gap-y-8 lg:grid-cols-2">
        <div>
          <Rise>
            <h2 id="sales-title" className={H2}>
              {word(change)} {Math.abs(change).toFixed(1)}%.
              <br />
              {word(without)} {Math.abs(without).toFixed(1)}% without Festive.
            </h2>
          </Rise>
          <Rise>
            <p className={clsx(LEAD, "mt-5 max-w-[48ch]")}>
              A headline number can mislead. {festival?.detail} ShelfIQ tells you that on the first line, instead of
              leaving you to find it in a spreadsheet.
            </p>
          </Rise>
        </div>
        <Rise>
          <div data-ui>
            <p className="text-[16px] font-medium">What moved revenue</p>
            <p className="num mb-3 text-[13px] text-muted">{signedInr(total)} vs same 28 days last year</p>
            <MovedBars rows={moved} />
          </div>
        </Rise>
      </div>
      <Rise className="mt-14">
        <div className="grid gap-x-10 gap-y-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,2.4fr)]">
          <p className={clsx(LEAD, "max-w-[28ch]")}>
            A struggling store shows up as a row, and a struggling category as a column.
          </p>
          <div data-ui className="overflow-x-auto">
            <SalesTable matrix={matrix} />
          </div>
        </div>
      </Rise>
    </section>
  );
}

/** Real answers from the analyst, with the numbers behind them. */
function Ask() {
  const [index, setIndex] = useState(5);
  const a = answers[index];
  const hasChart = a.chart.type !== "table";
  return (
    <section id="ask" aria-labelledby="ask-title" className={clsx(SECTION, "bg-hue-field text-white")}>
      <Rise>
        <h2 id="ask-title" className={H2}>
          Ask it why
        </h2>
      </Rise>
      <Rise>
        <p className={clsx(LEAD, "mt-4 max-w-[52ch]")}>
          Ask in your own words, the way you would ask an analyst, and get the answer with the numbers behind it.
        </p>
      </Rise>
      <div className="mt-10 grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)]">
        <Rise>
          <div role="tablist" aria-label="Questions" className="grid gap-1">
            {answers.map((q, i) => (
              <button
                key={q.question}
                role="tab"
                aria-selected={i === index}
                onClick={() => setIndex(i)}
                className={clsx(
                  "px-3 py-2 text-left text-[16px] leading-snug transition-colors md:text-[20px]",
                  i === index ? "bg-white text-[#141414]" : "text-white/85 hover:bg-white/10 hover:text-white",
                )}
              >
                {q.question}
              </button>
            ))}
          </div>
        </Rise>
        <Rise>
          <div data-ui className="min-h-[420px] rounded-lg bg-surface p-6 text-ink">
            <p className="text-[20px] leading-snug">{a.answer}</p>
            <p className="mt-4 mb-2 text-[13px] text-muted">{a.title}</p>
            {hasChart ? (
              <ResultChart spec={a.chart} columns={a.columns} rows={a.rows} />
            ) : (
              <div className="max-h-[280px] overflow-auto">
                <table className="w-full text-[13px]">
                  <thead className="sticky top-0 bg-surface text-muted">
                    <tr>
                      {a.columns.map((c, j) => (
                        <th
                          key={c}
                          className={clsx(
                            "py-1 pr-3 font-normal whitespace-nowrap",
                            typeof a.rows[0]?.[j] === "number" ? "text-right" : "text-left",
                          )}
                        >
                          {humanize(c)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {a.rows.map((row, i) => (
                      <tr key={i} className={"border-t border-rule" /* taste-skill-ignore: rule inside a data-ui fragment (a real table or slip) */}>
                        {row.map((v, j) => (
                          <td key={j} className={clsx("py-1 pr-3 whitespace-nowrap", typeof v === "number" && "num text-right")}>
                            {formatCell(a.columns[j], v)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </Rise>
      </div>
    </section>
  );
}

/** Why to trust the forecast, said in a retailer's words. */
function Forecast() {
  const methods = [
    ["ShelfIQ forecast", accuracy.wape_model],
    ["Average of the last 4 weeks", accuracy.wape_moving_avg],
    ["Same as last week", accuracy.wape_naive],
    ["Same week last year", accuracy.wape_seasonal_naive],
  ] as const;
  const top = Math.max(...methods.map(([, v]) => v ?? 0));
  return (
    <section aria-labelledby="forecast-title" className={SECTION}>
      <div className="grid gap-x-10 gap-y-8 lg:grid-cols-2">
        <div>
          <Rise>
            <h2 id="forecast-title" className={H2}>
              A forecast that knows your calendar
            </h2>
          </Rise>
          <Rise>
            <p className={clsx(LEAD, "mt-5 max-w-[48ch]")}>
              Diwali moves every year and promotions change what sells. ShelfIQ plans around both, eight weeks ahead,
              for every product in every store.
            </p>
          </Rise>
        </div>
        <Rise>
          <p className="text-[16px] font-medium">How far off each method was</p>
          <p className="mb-4 text-[13px] text-muted">
            The last {accuracy.backtest_weeks} weeks, checked against what actually sold. Lower is better.
          </p>
          <ul className="grid gap-3 text-[16px]">
            {methods.map(([name, value], i) =>
              value === null ? null : (
                <li key={name}>
                  <div className="flex justify-between">
                    <span className={clsx(i === 0 && "font-medium")}>{name}</span>
                    <span className={clsx("num", i === 0 && "font-bold")}>{(value * 100).toFixed(1)}%</span>
                  </div>
                  <span className="mt-1 block h-1.5 rounded-full bg-raised">
                    <span
                      className="block h-1.5 rounded-full"
                      style={{
                        width: `${(value / top) * 100}%`,
                        background: i === 0 ? "var(--hue)" : "var(--comparison)",
                      }}
                    />
                  </span>
                </li>
              ),
            )}
          </ul>
        </Rise>
      </div>
    </section>
  );
}

function Closing() {
  return (
    <section aria-labelledby="closing-title" className="bg-field px-4 py-20 text-white md:px-8 md:py-24">
      <div className="flex flex-wrap items-end justify-between gap-8">
        <Rise>
          <h2 id="closing-title" className={H2}>
            See it on a real morning
          </h2>
          <p className={clsx(LEAD, "mt-4 max-w-[46ch]")}>
            No sign-up. Open a demo chain of eight stores, as it stood on{" "}
            {formatDate(snapshot.as_of, { year: "numeric" })}, and look around.
          </p>
        </Rise>
        <Rise>
          <DemoButton />
        </Rise>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="flex flex-wrap items-center justify-between gap-4 bg-field px-4 pb-8 text-[13px] leading-[1.6] text-white/75 md:px-8">
      <p className="flex items-center gap-2 font-medium text-white">
        <ShelfMark size={16} /> ShelfIQ
      </p>
      <p>
        Photograph:{" "}
        <a className="underline" href="https://commons.wikimedia.org/wiki/File:Kirana_shop.jpg">
          Kirana shop
        </a>{" "}
        by Renzilde, CC BY-SA 3.0, via Wikimedia Commons.
      </p>
    </footer>
  );
}

export function Landing() {
  const [selected, setSelected] = useState<AlertRow>(worst[0]);
  return (
    <main>
      <Hero />
      <ProductWindow />
      <Questions />
      <Shelves selected={selected} onSelect={setSelected} />
      <Sales />
      <Ask />
      <Forecast />
      <Closing />
      <Footer />
    </main>
  );
}
