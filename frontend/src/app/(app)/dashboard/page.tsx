"use client";

import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { MovedBars, SalesTable, signedInr } from "@/components/analysis";
import { TitleRow } from "@/components/app-shell";
import { LegendItem, type Metric, MetricChart } from "@/components/charts";
import { ShelfSwatch, ShelfWall } from "@/components/shelf-wall";
import { Bar, BlockError, Change, CoverBar, Panel, Segmented } from "@/components/ui";
import {
  type Alerts,
  api,
  type Breakdown,
  type Kpi,
  type Matrix,
  type Products,
  type Summary,
  type Trend,
  type Upcoming,
} from "@/lib/api";
import { formatDate, formatInr, formatNumber } from "@/lib/format";
import { useScope } from "@/lib/scope";

const PERIODS = [
  { value: 7, label: "7 days" },
  { value: 28, label: "28 days" },
  { value: 91, label: "Quarter" },
  { value: 364, label: "Year" },
];

const METRIC_BY_KPI: Record<string, Metric> = {
  revenue: "revenue",
  units: "units",
  gross_margin: "margin_pct",
  promo_share: "promo_pct",
};

/** The screen's one finding. When Diwali distorts the comparison, take it out and say so. */
function finding(summary: Summary, categories: Breakdown | undefined): string {
  const revenue = summary.kpis.find((k) => k.key === "revenue");
  if (!revenue || revenue.change_pct === null) return "";
  const change = revenue.change_pct;
  const lead = `Revenue is ${change >= 0 ? "up" : "down"} ${Math.abs(change).toFixed(1)}% on the same ${summary.period_days} days last year`;
  const festival = summary.insights.find((i) => i.kind === "festival");
  const rest = categories?.rows.filter((r) => r.name !== "Festive & Gifting" && r.revenue_ly);
  if (festival && rest?.length) {
    const now = rest.reduce((sum, r) => sum + r.revenue, 0);
    const before = rest.reduce((sum, r) => sum + (r.revenue_ly ?? 0), 0);
    const without = ((now - before) / before) * 100;
    const joiner = without >= 0 === change >= 0 ? "and" : "but";
    return `${lead}, ${joiner} ${without >= 0 ? "up" : "down"} ${Math.abs(without).toFixed(1)}% without the Diwali shift in Festive & Gifting.`;
  }
  const store = summary.insights.find((i) => i.kind === "store");
  return store ? `${lead}. ${store.title}.` : `${lead}.`;
}

export default function OverviewPage() {
  const { storeId, setStoreId, store } = useScope();
  const router = useRouter();
  const [days, setDays] = useState(28);
  const [kpi, setKpi] = useState("revenue");
  const params = { days, store_id: storeId };

  const summary = useQuery({
    queryKey: ["summary", params],
    queryFn: () => api<Summary>("/api/dashboard/summary", params),
  });
  const trend = useQuery({
    queryKey: ["trend", storeId, days],
    queryFn: () =>
      api<Trend>("/api/dashboard/trend", { weeks: days === 364 ? 52 : 26, store_id: storeId }),
  });
  const categories = useQuery({
    queryKey: ["breakdown", "category", days, storeId],
    queryFn: () => api<Breakdown>("/api/dashboard/breakdown", { ...params, dimension: "category" }),
  });
  const alerts = useQuery({
    queryKey: ["alerts", "stockout_risk", storeId, 6],
    queryFn: () =>
      api<Alerts>("/api/forecast/alerts", { status: "stockout_risk", store_id: storeId, limit: 6 }),
  });
  const shelves = useQuery({
    queryKey: ["alerts", "all"],
    queryFn: () => api<Alerts>("/api/forecast/alerts", { status: "all", limit: 400 }),
  });
  const count = alerts.data?.counts.stockout_risk;

  return (
    <>
      <TitleRow
        title={store ? `${store.name}, ${store.city}` : "Overview"}
        finding={
          summary.data ? (
            finding(summary.data, categories.data)
          ) : (
            <Bar className="mt-1.5 h-4 w-96 max-w-full" />
          )
        }
        actions={<Segmented label="Period" value={days} options={PERIODS} onChange={setDays} />}
      />

      <div className="grid grid-cols-[minmax(0,1fr)] gap-4">
        <section className="rounded-lg border border-line bg-surface">
          <KpiTabs summary={summary} selected={kpi} onSelect={setKpi} />
          <div className="min-w-0 p-5">
            <div className="flex justify-end gap-4">
              <LegendItem label="This year" kind="line" color="var(--hue)" />
              <LegendItem label="Same week last year" kind="line" color="var(--comparison)" />
            </div>
            {trend.data ? (
              <MetricChart trend={trend.data} metric={METRIC_BY_KPI[kpi]} height={270} />
            ) : trend.isError ? (
              <div className="mt-4">
                <BlockError message={trend.error.message} onRetry={() => trend.refetch()} />
              </div>
            ) : (
              <Bar className="mt-2 h-[270px] w-full" />
            )}
          </div>
        </section>

        <ShelfWall
          rows={shelves.data?.rows}
          storeId={storeId}
          onPick={(r) => router.push(`/forecast?store=${r.store_id}&product=${r.product_id}`)}
          aside={
            <>
              <h2 className="text-[15px] font-semibold">Every shelf, right now</h2>
              <p className="mt-3 font-voice text-[36px] leading-[42px] font-medium tracking-[-0.015em]">
                <span className="num">{alerts.data ? count : "—"}</span>{" "}
                <span className="text-[17px] font-normal">run out before restock</span>
              </p>
              <p className="mt-1 text-sm text-band-muted">
                {alerts.data ? `${formatInr(alerts.data.revenue_at_risk, true)} of sales at risk` : " "}
              </p>
              <ul className="mt-3 flex flex-wrap gap-x-3 gap-y-1 text-[13px] text-band-muted">
                <li className="flex items-center gap-1.5"><ShelfSwatch status="stockout_risk" /> Runs out</li>
                <li className="flex items-center gap-1.5"><ShelfSwatch status="overstock" /> Overstocked</li>
                <li className="flex items-center gap-1.5"><ShelfSwatch status="healthy" /> Healthy</li>
              </ul>
              {!!count && (
                <Link
                  href="/forecast"
                  className="mt-4 inline-flex h-9 items-center gap-1.5 rounded-md bg-band-ink px-3.5 text-sm font-medium text-band transition-colors hover:bg-white"
                >
                  Review {count} <ArrowRight className="size-4" aria-hidden />
                </Link>
              )}
            </>
          }
        />

        <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-4 xl:grid-cols-2">
          <RunsOut alerts={alerts} />
          <WhatMoved days={days} storeId={storeId} />
        </div>

        <MoreDetail days={days} storeId={storeId} onSelectStore={setStoreId} />
      </div>
    </>
  );
}

function kpiValue(k: Kpi) {
  if (k.unit === "inr") return formatInr(k.value, true);
  if (k.unit === "pct") return `${k.value.toFixed(1)}%`;
  return formatNumber(k.value, true);
}

/** The headline figures are also the chart's tabs; the selected one carries a 2px rule. */
function KpiTabs({
  summary,
  selected,
  onSelect,
}: {
  summary: ReturnType<typeof useQuery<Summary>>;
  selected: string;
  onSelect: (key: string) => void;
}) {
  const kpis = summary.data?.kpis;
  if (summary.isError) {
    return (
      <div className="p-5">
        <BlockError message={summary.error.message} onRetry={() => summary.refetch()} />
      </div>
    );
  }
  return (
    <div role="tablist" aria-label="Chart metric" className="grid grid-cols-2 border-b border-line lg:grid-cols-4">
      {(kpis ?? [null, null, null, null]).map((k, i) => (
        <button
          key={k?.key ?? i}
          role="tab"
          aria-selected={k?.key === selected}
          onClick={() => k && onSelect(k.key)}
          className={clsx(
            "-mb-px border-b-2 px-5 py-4 text-left transition-colors hover:bg-hover",
            k?.key === selected ? "border-hue" : "border-transparent",
          )}
        >
          <span className="block text-sm text-muted">{k?.label ?? <Bar className="h-4 w-24" />}</span>
          {k ? (
            <>
              <span
                className={clsx(
                  "num mt-0.5 block font-voice leading-10 font-medium tracking-[-0.015em] whitespace-nowrap",
                  k.key === "revenue" ? "text-[30px] sm:text-[36px]" : "text-[26px]",
                )}
              >
                {kpiValue(k)}
              </span>
              <span className="block text-[13px]">
                <Change
                  value={k.change_pct}
                  unit={k.unit === "pct" ? " pts" : "%"}
                  threshold={k.key === "promo_share" ? Infinity : 0.5}
                  baseline="vs last year"
                />
              </span>
            </>
          ) : (
            <Bar className="mt-1 h-12 w-28" />
          )}
        </button>
      ))}
    </div>
  );
}

/** Where the change in revenue came from, in rupees, on one zero line. */
function WhatMoved({ days, storeId }: { days: number; storeId: string }) {
  const [dimension, setDimension] = useState<"category" | "store">("category");
  const dim = storeId ? "category" : dimension;
  const q = useQuery({
    queryKey: ["breakdown", dim, days, storeId],
    queryFn: () =>
      api<Breakdown>("/api/dashboard/breakdown", { days, store_id: storeId, dimension: dim }),
  });
  const rows = (q.data?.rows ?? [])
    .map((r) => ({
      name: dim === "store" ? r.name.split(",")[0] : r.name,
      delta: r.revenue - (r.revenue_ly ?? 0),
    }))
    .sort((a, b) => b.delta - a.delta);
  const total = rows.reduce((sum, r) => sum + r.delta, 0);

  return (
    <Panel
      title="What moved revenue"
      meta={q.data ? <span className="num">{signedInr(total)}</span> : undefined}
      action={
        !storeId && (
          <Segmented
            label="Break down by"
            value={dimension}
            onChange={setDimension}
            options={[
              { value: "category", label: "Category" },
              { value: "store", label: "Store" },
            ]}
            small
          />
        )
      }
    >
      {q.isError ? (
        <BlockError message={q.error.message} onRetry={() => q.refetch()} />
      ) : q.data ? (
        <MovedBars rows={rows.slice(0, 6)} />
      ) : (
        <div className="grid gap-1.5">
          {Array.from({ length: 6 }, (_, i) => (
            <Bar key={i} className="h-9 w-full" />
          ))}
        </div>
      )}
    </Panel>
  );
}

type Detail = "stores" | "products" | "coming";

/** The next questions, one at a time, so the screen stays readable. */
function MoreDetail({
  days,
  storeId,
  onSelectStore,
}: {
  days: number;
  storeId: string;
  onSelectStore: (id: string) => void;
}) {
  const [tab, setTab] = useState<Detail>("stores");
  const tabs: [Detail, string][] = [
    ["stores", "Stores"],
    ["products", "Products"],
    ["coming", "Coming up"],
  ];
  return (
    <section className="rounded-lg border border-line bg-surface">
      <div role="tablist" aria-label="More detail" className="flex gap-6 border-b border-line px-5">
        {tabs.map(([value, label]) => (
          <button
            key={value}
            role="tab"
            aria-selected={tab === value}
            onClick={() => setTab(value)}
            className={clsx(
              "-mb-px h-11 border-b-2 text-sm transition-colors",
              tab === value ? "border-hue font-medium" : "border-transparent text-muted hover:text-ink",
            )}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="p-5">
        {tab === "stores" && <SalesMap days={days} storeId={storeId} onSelect={onSelectStore} />}
        {tab === "products" && <ProductList days={days} storeId={storeId} />}
        {tab === "coming" && <ComingUp />}
      </div>
    </section>
  );
}

/** ShelfIQ's map of the chain: revenue change for every store and category. */
function SalesMap({
  days,
  storeId,
  onSelect,
}: {
  days: number;
  storeId: string;
  onSelect: (id: string) => void;
}) {
  const q = useQuery({
    queryKey: ["matrix", days],
    queryFn: () => api<Matrix>("/api/dashboard/matrix", { days }),
  });
  const worst = q.data?.rows.reduce((a, b) => ((a.yoy_pct ?? 0) < (b.yoy_pct ?? 0) ? a : b));
  const down = worst?.cells.filter((c) => (c.yoy_pct ?? 0) < 0).length;
  if (q.isError) return <BlockError message={q.error.message} onRetry={() => q.refetch()} />;
  if (!q.data) return <Bar className="h-80 w-full" />;
  return (
    <>
      <p className="mb-3 text-sm text-muted">
        {worst && (worst.yoy_pct ?? 0) < 0
          ? `Change vs last year. ${worst.store.split(",")[0]} is behind in ${down} of ${worst.cells.length} categories.`
          : "Change vs last year."}
      </p>
      <div className="overflow-x-auto">
        <SalesTable matrix={q.data} selected={storeId} onSelect={onSelect} />
      </div>
    </>
  );
}

function daysLeft(cover: number | null | undefined) {
  if (cover === null || cover === undefined) return "no recent sales";
  if (cover < 1) return "under a day left";
  const days = Math.round(cover);
  return `${days} ${days === 1 ? "day" : "days"} left`;
}

function RunsOut({ alerts }: { alerts: ReturnType<typeof useQuery<Alerts>> }) {
  const data = alerts.data;
  return (
    <Panel title="Biggest sales at risk">

      {alerts.isError ? (
        <BlockError message={alerts.error.message} onRetry={() => alerts.refetch()} />
      ) : (
        <ul>
          {(data?.rows ?? Array.from({ length: 6 }, () => null)).map((r, i) => (
            <li
              key={r ? `${r.store_id}-${r.product_id}` : i}
              className="grid min-h-[52px] grid-cols-[minmax(0,1fr)_60px] items-center gap-x-4 border-t border-rule py-1.5 first:border-t-0 sm:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)_60px]"
            >
              {r ? (
                <>
                  <div className="min-w-0">
                    <p className="truncate font-medium">{r.product_name}</p>
                    <p className="truncate text-[13px] text-muted">
                      {r.store_name.split(",")[0]}, {daysLeft(r.days_of_cover)}
                    </p>
                  </div>
                  <span className="hidden sm:block">
                    <CoverBar cover={r.days_of_cover} leadTime={r.lead_time_days} />
                  </span>
                  <p className="num text-right font-medium">{formatInr(r.revenue_at_risk, true)}</p>
                </>
              ) : (
                <>
                  <Bar className="h-4 w-32" />
                  <Bar className="h-3 w-full" />
                  <Bar className="ml-auto h-4 w-12" />
                </>
              )}
            </li>
          ))}
          {data && data.rows.length === 0 && (
            <li className="text-sm text-muted">Nothing here will run out before it can be restocked.</li>
          )}
        </ul>
      )}
    </Panel>
  );
}

function ProductList({ days, storeId }: { days: number; storeId: string }) {
  const [sort, setSort] = useState<"top" | "declining">("top");
  const q = useQuery({
    queryKey: ["products", sort, days, storeId],
    queryFn: () =>
      api<Products>("/api/dashboard/products", { days, store_id: storeId, sort, limit: 6 }),
  });
  return (
    <>
      <div className="mb-2">
        <Segmented
          label="Product ranking"
          value={sort}
          onChange={setSort}
          options={[
            { value: "top", label: "Top sellers" },
            { value: "declining", label: "Declining" },
          ]}
          small
        />
      </div>
      {q.isError ? (
        <BlockError message={q.error.message} onRetry={() => q.refetch()} />
      ) : (
        <table className="w-full text-sm">
          <thead className="text-xs text-muted">
            <tr>
              <th className="pb-2 text-left font-normal">Product</th>
              <th className="hidden pb-2 text-right font-normal sm:table-cell">Units</th>
              <th className="pb-2 text-right font-normal">Revenue</th>
              <th className="pb-2 text-right font-normal">Change</th>
            </tr>
          </thead>
          <tbody>
            {(q.data?.rows ?? Array.from({ length: 6 }, () => null)).map((p, i) => (
              <tr key={p?.product_id ?? i} className="border-t border-rule">
                <td className="py-2 pr-4">
                  {p ? (
                    <>
                      {p.name}
                      <span className="block text-[13px] text-muted">{p.category}</span>
                    </>
                  ) : (
                    <Bar className="h-9 w-40" />
                  )}
                </td>
                <td className="num hidden py-2 text-right text-muted sm:table-cell">
                  {p && formatNumber(p.units)}
                </td>
                <td className="num py-2 text-right">{p && formatInr(p.revenue, true)}</td>
                <td className="num py-2 text-right">{p && <Change value={p.yoy_pct} threshold={5} />}</td>
              </tr>
            ))}
            {q.data && q.data.rows.length === 0 && (
              <tr>
                <td colSpan={4} className="py-3 text-muted">
                  No product fell noticeably against last year.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      )}
    </>
  );
}

/** What is about to change demand: the festival countdown and planned promotions. */
function ComingUp() {
  const q = useQuery({
    queryKey: ["upcoming"],
    queryFn: () => api<Upcoming>("/api/dashboard/upcoming", { days: 14, limit: 5 }),
  });
  const u = q.data;
  return (
    <>
      {q.isError ? (
        <BlockError message={q.error.message} onRetry={() => q.refetch()} />
      ) : !u ? (
        <Bar className="h-72 w-full" />
      ) : (
        <>
          {u.festival && u.festival_date && (
            <p>
              <span className="num text-[26px] leading-9 font-medium tracking-[-0.01em]">
                {u.days_to_festival} days
              </span>{" "}
              <span className="text-muted">
                to {u.festival}, {formatDate(u.festival_date, { year: "numeric" })}
              </span>
            </p>
          )}
          <ul className="mt-2">
            {u.promotions.map((p) => (
              <li
                key={`${p.product}-${p.start_date}`}
                className="flex items-center justify-between gap-3 border-t border-rule py-2"
              >
                <span className="min-w-0">
                  <span className="block truncate">{p.product}</span>
                  <span className="block truncate text-[13px] text-muted">
                    {formatDate(p.start_date)} to {formatDate(p.end_date)}
                  </span>
                </span>
                <span className="num flex-none">{p.discount_pct}% off</span>
              </li>
            ))}
            {u.promotions.length === 0 && (
              <li className="border-t border-rule py-2 text-muted">No promotions start in the next 14 days.</li>
            )}
          </ul>
        </>
      )}
    </>
  );
}
