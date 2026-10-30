"use client";

import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { ArrowDown, Download, Search, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { TitleRow } from "@/components/app-shell";
import { ForecastChart, LegendItem } from "@/components/charts";
import { ShelfSwatch, ShelfWall } from "@/components/shelf-wall";
import { StockRunway } from "@/components/stock-runway";
import { Select } from "@/components/select";
import { Bar, BlockError, Button, CoverBar, Disclosure, Panel, Pill, Segmented } from "@/components/ui";
import { type AlertRow, type Alerts, api, type ForecastMetrics, type ForecastSeries } from "@/lib/api";
import { formatInr } from "@/lib/format";
import { useScope } from "@/lib/scope";

type Status = "stockout_risk" | "healthy" | "overstock";
type Selected = { store: number; product: number };
type Sort = "impact" | "cover";

/** Days of extra cover a reorder should buy beyond the lead time. */
const SAFETY_DAYS = 14;
/** Stock beyond this many days of selling counts as tied up. */
const OVERSTOCK_DAYS = 60;
const PAGE = 10;

function suggestedOrder(row: AlertRow): number {
  return Math.max(0, Math.ceil(row.daily_demand * (row.lead_time_days + SAFETY_DAYS) - row.on_hand));
}

function tiedUp(row: AlertRow): number {
  return Math.max(0, row.on_hand - row.daily_demand * OVERSTOCK_DAYS) * row.unit_price;
}

function impact(row: AlertRow): number {
  return row.status === "overstock" ? tiedUp(row) : row.revenue_at_risk;
}

function downloadReorderList(rows: AlertRow[], asOf: string) {
  const header = [
    "store",
    "sku",
    "product",
    "on_hand",
    "daily_demand",
    "days_of_cover",
    "lead_time_days",
    "suggested_order_units",
    "sales_at_risk_inr",
  ];
  const quote = (v: string | number | null) => {
    const s = v === null ? "" : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const lines = rows.map((r) =>
    [
      r.store_name,
      r.sku,
      r.product_name,
      r.on_hand,
      r.daily_demand,
      r.days_of_cover,
      r.lead_time_days,
      suggestedOrder(r),
      r.revenue_at_risk,
    ]
      .map(quote)
      .join(","),
  );
  const blob = new Blob([[header.join(","), ...lines].join("\n")], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `shelfdekho-reorder-${asOf}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

export default function StockPage() {
  const { storeId, setStoreId, store } = useScope();
  const [status, setStatus] = useState<Status>("stockout_risk");
  const [selected, setSelected] = useState<Selected | null>(null);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [sort, setSort] = useState<Sort>("impact");
  const [limit, setLimit] = useState(PAGE);
  const listRef = useRef<HTMLElement>(null);
  const detailRef = useRef<HTMLDivElement>(null);

  // Every store x SKU, once: tabs, map and filters then work instantly on the client.
  const q = useQuery({
    queryKey: ["alerts", "all"],
    queryFn: () => api<Alerts>("/api/forecast/alerts", { status: "all", limit: 400 }),
  });
  const all = useMemo(() => q.data?.rows ?? [], [q.data]);
  const scoped = useMemo(
    () => all.filter((r) => !storeId || String(r.store_id) === storeId),
    [all, storeId],
  );

  const position = useMemo(() => {
    const of = (s: Status) => scoped.filter((r) => r.status === s);
    return {
      risk: of("stockout_risk"),
      healthy: of("healthy"),
      over: of("overstock"),
      atRisk: of("stockout_risk").reduce((sum, r) => sum + r.revenue_at_risk, 0),
      tied: of("overstock").reduce((sum, r) => sum + tiedUp(r), 0),
    };
  }, [scoped]);

  const rows = useMemo(() => {
    const term = search.trim().toLowerCase();
    return scoped
      .filter(
        (r) =>
          r.status === status &&
          (!category || r.category === category) &&
          (!term || `${r.product_name} ${r.sku} ${r.store_name}`.toLowerCase().includes(term)),
      )
      .sort((a, b) =>
        sort === "cover"
          ? (a.days_of_cover ?? Infinity) - (b.days_of_cover ?? Infinity)
          : impact(b) - impact(a) || (a.days_of_cover ?? 0) - (b.days_of_cover ?? 0),
      );
  }, [scoped, status, category, search, sort]);

  const first = rows[0];
  const active = selected ?? (first ? { store: first.store_id, product: first.product_id } : null);
  const activeRow = all.find((r) => r.store_id === active?.store && r.product_id === active?.product);
  const categories = useMemo(() => [...new Set(all.map((r) => r.category))].sort(), [all]);

  const reset = () => {
    setSelected(null);
    setLimit(PAGE);
  };

  const pick = (r: AlertRow) => {
    setStatus(r.status as Status);
    setSelected({ store: r.store_id, product: r.product_id });
    setLimit(PAGE);
    if (window.innerWidth < 1280) {
      detailRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  // Arriving from a shelf on the Overview wall: open on that shelf.
  const arrived = useRef(false);
  useEffect(() => {
    if (arrived.current || all.length === 0) return;
    arrived.current = true;
    const params = new URLSearchParams(window.location.search);
    const shelf = all.find(
      (r) =>
        String(r.store_id) === params.get("store") && String(r.product_id) === params.get("product"),
    );
    if (shelf) {
      setStatus(shelf.status as Status);
      setSelected({ store: shelf.store_id, product: shelf.product_id });
    }
  }, [all]);

  return (
    <>
      <TitleRow
        title={store ? `Stock at ${store.name}` : "Stock"}
        finding={
          q.data ? (
            `${position.risk.length} shelves will run out before a reorder can arrive, putting ${formatInr(position.atRisk, true)} of sales at risk.`
          ) : (
            <Bar className="mt-1.5 h-4 w-96 max-w-full" />
          )
        }
        actions={
          <Button
            variant="primary"
            disabled={!q.data || status !== "stockout_risk" || rows.length === 0}
            onClick={() => q.data && downloadReorderList(rows, q.data.as_of)}
          >
            <Download className="size-4" strokeWidth={1.8} aria-hidden />
            Download reorder list
          </Button>
        }
      />

      <ShelfWall
        rows={q.data?.rows}
        storeId={storeId}
        emphasis={status}
        selected={active}
        onPick={pick}
        aside={
          <StatusTabs
            status={status}
            counts={{
              stockout_risk: q.data ? position.risk.length : null,
              overstock: q.data ? position.over.length : null,
              healthy: q.data ? position.healthy.length : null,
            }}
            notes={{
              stockout_risk: q.data ? `${formatInr(position.atRisk, true)} of sales at risk` : "",
              overstock: q.data ? `${formatInr(position.tied, true)} tied up` : "",
              healthy: "Covered past the next delivery",
            }}
            onSelect={(s) => {
              setStatus(s);
              reset();
            }}
          />
        }
      />

      <div className="mt-4 grid grid-cols-[minmax(0,1fr)] items-start gap-4 xl:grid-cols-[minmax(0,1fr)_400px]">
        <section ref={listRef} className="scroll-mt-4 rounded-lg border border-line bg-surface">
          <div className="flex flex-wrap items-center gap-2 px-5 pt-4">
            <label className="relative min-w-0 flex-1 basis-48">
              <span className="sr-only">Search products or stores</span>
              <Search className="absolute top-2.5 left-2.5 size-4 text-muted" strokeWidth={1.8} aria-hidden />
              <input
                type="search"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  reset();
                }}
                placeholder="Search product, SKU or store"
                className="h-9 w-full rounded-md border border-control bg-surface pr-2.5 pl-8 text-sm placeholder:text-muted"
              />
            </label>
            <Select
              label="Category"
              value={category}
              onChange={(v) => {
                setCategory(v);
                reset();
              }}
              options={[
                { value: "", label: "All categories" },
                ...categories.map((c) => ({ value: c, label: c })),
              ]}
              className="w-48"
            />
            {(search || category) && (
              <button
                onClick={() => {
                  setSearch("");
                  setCategory("");
                  reset();
                }}
                className="inline-flex h-9 items-center gap-1 px-1 text-sm text-muted hover:text-ink"
              >
                <X className="size-3.5" aria-hidden /> Clear
              </button>
            )}
          </div>
          {q.isError ? (
            <div className="p-5">
              <BlockError message={q.error.message} onRetry={() => q.refetch()} />
            </div>
          ) : (
            <ShelfList
              rows={q.data ? rows : undefined}
              limit={limit}
              onMore={() => setLimit(rows.length)}
              status={status}
              sort={sort}
              onSort={setSort}
              active={active}
              onSelect={(r) => {
                setSelected({ store: r.store_id, product: r.product_id });
                // Below xl the detail sits under the list: take the reader to it.
                if (window.innerWidth < 1280) {
                  detailRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
                }
              }}
            />
          )}
        </section>

        <div ref={detailRef} className="scroll-mt-4 xl:sticky xl:top-4">
          <Detail active={active} row={activeRow} asOf={q.data?.as_of} />
        </div>
      </div>

      <div className="mt-4 grid grid-cols-[minmax(0,1fr)] gap-2">
        <RiskMap
          rows={all}
          categories={categories}
          loading={!q.data}
          onSelect={(storeValue, categoryValue) => {
            setStoreId(storeValue);
            setCategory(categoryValue);
            setStatus("stockout_risk");
            reset();
            listRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
          }}
        />
        <Accuracy />
      </div>
    </>
  );
}

const STATUS_LABELS: [Status, string][] = [
  ["stockout_risk", "Runs out"],
  ["overstock", "Overstocked"],
  ["healthy", "Healthy"],
];

/** Which shelves the wall lights up and the list shows. Each count is also the wall's legend. */
function StatusTabs({
  status,
  counts,
  notes,
  onSelect,
}: {
  status: Status;
  counts: Record<Status, number | null>;
  notes: Record<Status, string>;
  onSelect: (status: Status) => void;
}) {
  return (
    <div role="tablist" aria-label="Shelf position" className="-mx-2 grid gap-1 sm:grid-cols-3 xl:grid-cols-1">
      {STATUS_LABELS.map(([value, label]) => (
        <button
          key={value}
          role="tab"
          aria-selected={status === value}
          onClick={() => onSelect(value)}
          className={clsx(
            "rounded-md px-2.5 py-1.5 text-left transition-colors",
            status === value ? "bg-band-raised" : "hover:bg-band-raised/50",
          )}
        >
          <span className="flex items-center gap-2 text-[13px] text-band-muted">
            <ShelfSwatch status={value} /> {label}
          </span>
          <span
            className={clsx(
              "num block font-voice leading-8 font-medium tracking-[-0.015em]",
              value === "stockout_risk" ? "text-[30px]" : "text-[22px]",
            )}
          >
            {counts[value] ?? "—"}
          </span>
          <span className="block truncate text-xs text-band-muted">{notes[value]}</span>
        </button>
      ))}
    </div>
  );
}

function SortHead({
  value,
  sort,
  onSort,
  right,
  children,
}: {
  value: Sort;
  sort: Sort;
  onSort: (sort: Sort) => void;
  right?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={() => onSort(value)}
      className={clsx(
        "inline-flex items-center gap-1 hover:text-ink",
        right && "justify-end",
        sort === value && "text-ink",
      )}
    >
      {children}
      {sort === value && <ArrowDown className="size-3" aria-hidden />}
    </button>
  );
}

function ShelfList({
  rows,
  limit,
  onMore,
  status,
  sort,
  onSort,
  active,
  onSelect,
}: {
  rows: AlertRow[] | undefined;
  limit: number;
  onMore: () => void;
  status: Status;
  sort: Sort;
  onSort: (sort: Sort) => void;
  active: Selected | null;
  onSelect: (row: AlertRow) => void;
}) {
  const cols =
    "grid grid-cols-[minmax(0,1fr)_84px] items-center gap-x-4 sm:grid-cols-[minmax(0,1fr)_136px_72px_84px]";
  const impactLabel =
    status === "stockout_risk" ? "Sales at risk" : status === "overstock" ? "Tied up" : "Sells a day";
  return (
    <div>
      <div className={clsx(cols, "hidden px-5 pt-3 pb-1 text-xs text-muted sm:grid")}>
        <span>Product and store</span>
        <SortHead value="cover" sort={sort} onSort={onSort}>
          Cover vs reorder
        </SortHead>
        <span className="text-right">{status === "stockout_risk" ? "Order" : "Sells a day"}</span>
        <span className="text-right">
          {status === "healthy" ? (
            "Cover"
          ) : (
            <SortHead value="impact" sort={sort} onSort={onSort} right>
              {impactLabel}
            </SortHead>
          )}
        </span>
      </div>
      <ul className="mt-1 sm:mt-0">
        {(rows ? rows.slice(0, limit) : Array.from({ length: 8 }, () => null)).map((r, i) => {
          const isActive = r && active?.store === r.store_id && active?.product === r.product_id;
          const coverText = r
            ? r.days_of_cover === null
              ? "no demand"
              : `${r.days_of_cover.toFixed(1)} of ${r.lead_time_days} days`
            : "";
          return (
            <li key={r ? `${r.store_id}-${r.product_id}` : i} className="border-t border-rule">
              {r ? (
                <button
                  onClick={() => onSelect(r)}
                  aria-pressed={!!isActive}
                  className={clsx(
                    cols,
                    "w-full px-5 py-3 text-left transition-colors",
                    isActive ? "bg-active" : "hover:bg-hover",
                  )}
                >
                  <span className="min-w-0">
                    <span className="block truncate font-medium">{r.product_name}</span>
                    <span className="block truncate text-[13px] text-muted">
                      <span className="hidden sm:inline">{r.store_name.split(",")[0]}</span>
                      <span className="sm:hidden">
                        {r.store_name.split(",")[0]} · {coverText}
                      </span>
                    </span>
                  </span>
                  <span className="hidden sm:block">
                    <CoverBar
                      cover={r.days_of_cover}
                      leadTime={r.lead_time_days}
                      scaleDays={status === "stockout_risk" ? 28 : 120}
                    />
                    <span className="num mt-1 block text-[13px] text-muted">{coverText}</span>
                  </span>
                  <span className="num hidden text-right sm:block">
                    {status === "stockout_risk"
                      ? suggestedOrder(r).toLocaleString("en-IN")
                      : r.daily_demand.toFixed(1)}
                  </span>
                  <span className="num text-right font-medium">
                    {status === "healthy"
                      ? `${Math.round(r.days_of_cover ?? 0)} days`
                      : formatInr(impact(r), true)}
                  </span>
                </button>
              ) : (
                <div className={clsx(cols, "px-5 py-2.5")}>
                  <Bar className="h-9 w-48" />
                  <Bar className="hidden h-3 w-full sm:block" />
                  <Bar className="ml-auto hidden h-4 w-10 sm:block" />
                  <Bar className="ml-auto h-4 w-14" />
                </div>
              )}
            </li>
          );
        })}
      </ul>
      {rows && rows.length === 0 && (
        <p className="border-t border-rule px-5 py-4 text-sm text-muted">No shelves match this search.</p>
      )}
      {rows && rows.length > limit && (
        <button
          onClick={onMore}
          className="w-full border-t border-rule px-5 py-3 text-left text-sm font-medium hover:bg-hover"
        >
          Show all {rows.length}
        </button>
      )}
    </div>
  );
}

function Detail({
  active,
  row,
  asOf,
}: {
  active: Selected | null;
  row: AlertRow | undefined;
  asOf: string | undefined;
}) {
  const [view, setView] = useState<"runway" | "demand">("runway");
  const series = useQuery({
    queryKey: ["series", active],
    queryFn: () =>
      api<ForecastSeries>("/api/forecast/series", {
        store_id: active!.store,
        product_id: active!.product,
      }),
    enabled: active !== null,
  });
  const s = series.data;
  const stale = s && row && (s.product.id !== row.product_id || s.store.id !== row.store_id);
  return (
    <Panel
      title={row ? row.product_name : <Bar className="h-5 w-40" />}
      meta={row?.store_name.split(",")[0]}
      action={
        row &&
        row.status !== "healthy" && (
          <Pill tone={row.status === "stockout_risk" ? "negative" : "neutral"}>
            {row.status === "stockout_risk" ? "Runs out" : "Overstocked"}
          </Pill>
        )
      }
    >
      <div className="mb-3">
        <Segmented
          label="Detail view"
          value={view}
          onChange={setView}
          small
          options={[
            { value: "runway", label: "Runway" },
            { value: "demand", label: "Sales and forecast" },
          ]}
        />
      </div>
      {view === "runway" ? (
        <>
          {row && asOf ? (
            <StockRunway
              asOf={asOf}
              onHand={row.on_hand}
              dailyDemand={row.daily_demand}
              leadTime={row.lead_time_days}
              order={row.status === "overstock" ? 0 : suggestedOrder(row)}
            />
          ) : (
            <Bar className="h-32 w-full" />
          )}
          <dl className="mt-3 grid gap-x-6 text-sm min-[420px]:grid-cols-2">
            {[
              ["On hand", row ? `${row.on_hand.toLocaleString("en-IN")} units` : null],
              ["Sells a day", row ? row.daily_demand.toFixed(1) : null],
              ["Reorder takes", row ? `${row.lead_time_days} days` : null],
              ["Suggested order", row ? `${suggestedOrder(row).toLocaleString("en-IN")} units` : null],
            ].map(([label, value]) => (
              <div key={label} className="flex justify-between gap-2 border-t border-rule py-1.5 whitespace-nowrap">
                <dt className="text-muted">{label}</dt>
                <dd className="num font-medium">{value ?? <Bar className="h-4 w-14" />}</dd>
              </div>
            ))}
          </dl>
        </>
      ) : (
        <>
          <div className="flex flex-wrap gap-x-3">
            <LegendItem label="Sold" kind="line" color="var(--text)" />
            <LegendItem label="Forecast" kind="dash" color="var(--hue)" />
            {s?.points.some((p) => p.on_promo) && (
              <LegendItem label="Promotion" kind="span" color="var(--text)" />
            )}
          </div>
          {s && !stale ? (
            <ForecastChart series={s} height={230} />
          ) : series.isError ? (
            <BlockError message={series.error.message} onRetry={() => series.refetch()} />
          ) : (
            <Bar className="mt-1 h-[230px] w-full" />
          )}
        </>
      )}
    </Panel>
  );
}

/** Where the at-risk shelves sit across the chain. A cell filters the list to it. */
function RiskMap({
  rows,
  categories,
  loading,
  onSelect,
}: {
  rows: AlertRow[];
  categories: string[];
  loading: boolean;
  onSelect: (store: string, category: string) => void;
}) {
  const stores = [...new Map(rows.map((r) => [r.store_id, r.store_name])).entries()].sort(
    (a, b) => a[0] - b[0],
  );
  const risk = rows.filter((r) => r.status === "stockout_risk");
  const count = (store: number, category: string) =>
    risk.filter((r) => r.store_id === store && r.category === category).length;
  const max = Math.max(
    1,
    ...stores.flatMap(([id]) => categories.map((c) => count(id, c))),
  );
  const short = (c: string) => c.split(" ")[0];
  const riskAt = (store: number) => risk.filter((r) => r.store_id === store).length;
  const worst = stores.length ? stores.reduce((a, b) => (riskAt(b[0]) > riskAt(a[0]) ? b : a)) : null;
  return (
    <Disclosure
      title="Where the risk sits"
      summary={
        worst && riskAt(worst[0])
          ? `${worst[1].split(",")[0]} has the most, ${riskAt(worst[0])} of ${risk.length} shelves`
          : undefined
      }
    >
      {loading ? (
        <Bar className="h-72 w-full" />
      ) : (
        <table className="w-full min-w-[460px] border-separate border-spacing-0.5 text-[13px]">
          <thead className="text-muted">
            <tr>
              <th className="pb-1 text-left font-normal">Store</th>
              {categories.map((c) => (
                <th key={c} className="pb-1 text-right font-normal">
                  {short(c)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {stores.map(([id, name]) => (
              <tr key={id}>
                <th scope="row" className="pr-3 text-left font-normal whitespace-nowrap">
                  {name.split(",")[0]}
                </th>
                {categories.map((c) => {
                  const n = count(id, c);
                  return (
                    <td key={c} className="p-0">
                      <button
                        disabled={n === 0}
                        onClick={() => onSelect(String(id), c)}
                        aria-label={`${n} shelves running out: ${name}, ${c}`}
                        className={clsx(
                          "num block w-full rounded-[3px] px-2 py-[6px] text-right",
                          n === 0 ? "text-muted" : "font-medium hover:outline hover:outline-1 hover:outline-ink",
                        )}
                        style={n ? { background: `rgba(var(--heat-down), ${0.1 + (n / max) * 0.4})` } : undefined}
                      >
                        {n}
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Disclosure>
  );
}

function Accuracy() {
  const q = useQuery({
    queryKey: ["forecast-metrics"],
    queryFn: () => api<ForecastMetrics>("/api/forecast/metrics"),
  });
  const m = q.data;
  const rows = m
    ? [
        { name: "ShelfDekho forecast", wape: m.wape_model, ours: true },
        { name: "Average of the last 4 weeks", wape: m.wape_moving_avg },
        { name: "Same as last week", wape: m.wape_naive },
        ...(m.wape_seasonal_naive !== null
          ? [{ name: "Same week last year", wape: m.wape_seasonal_naive }]
          : []),
      ].sort((a, b) => a.wape - b.wape)
    : [];
  const max = Math.max(...rows.map((r) => r.wape), 0.01);

  return (
    <Disclosure
      title="How good is the forecast"
      summary={m ? `${m.improvement_pct.toFixed(0)}% closer than the best simple method, over the last ${m.backtest_weeks} weeks` : undefined}
    >
      {q.isError ? (
        <BlockError message={q.error.message} onRetry={() => q.refetch()} />
      ) : !m ? (
        <Bar className="h-64 w-full" />
      ) : (
        <>
          <ul className="grid max-w-xl gap-2.5" aria-label="Weighted absolute percentage error by method">
            {rows.map((r) => (
              <li key={r.name} className="text-sm">
                <div className="flex justify-between">
                  <span className={clsx(r.ours && "font-medium")}>{r.name}</span>
                  <span className="num">{(r.wape * 100).toFixed(1)}%</span>
                </div>
                <span className="mt-1 block h-1.5 rounded-full bg-raised">
                  <span
                    className="block h-1.5 rounded-full"
                    style={{
                      width: `${(r.wape / max) * 100}%`,
                      background: r.ours ? "var(--hue)" : "var(--comparison)",
                    }}
                  />
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-[13px] text-muted">
            How far off each method was, across {m.series_count} shelves. The forecast plans around promotions and
            the date of Diwali.
          </p>
        </>
      )}
    </Disclosure>
  );
}
