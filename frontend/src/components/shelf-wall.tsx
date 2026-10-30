"use client";

import clsx from "clsx";
import { type ReactNode, useMemo, useState } from "react";
import type { AlertRow } from "@/lib/api";
import { Bar } from "./ui";

const SHORT_CATEGORY: Record<string, string> = {
  "Snacks & Beverages": "Snacks",
  "Personal Care": "Personal care",
  "Home Care": "Home care",
  "Festive & Gifting": "Festive",
};

const SHELF_COLOUR: Record<string, string> = {
  stockout_risk: "var(--shelf-risk)",
  overstock: "var(--shelf-over)",
  healthy: "var(--shelf-ok)",
};

function describe(r: AlertRow) {
  const store = r.store_name.split(",")[0];
  if (r.days_of_cover === null) return `${r.product_name} at ${store}: no recent sales.`;
  const days = r.days_of_cover < 1 ? "under a day" : `${r.days_of_cover.toFixed(1)} days`;
  return `${r.product_name} at ${store}: ${days} of stock, reorder takes ${r.lead_time_days}.`;
}

export function ShelfSwatch({ status }: { status: string }) {
  return (
    <span
      className="inline-block h-3 w-2.5 flex-none rounded-[2px]"
      style={{ background: SHELF_COLOUR[status] }}
      aria-hidden
    />
  );
}

/**
 * ShelfDekho's own element: every product in every store, one mark each, laid out like the bays
 * of a shop. A bad store reads as a row and a bad category as a column.
 */
export function ShelfWall({
  rows,
  storeId,
  emphasis,
  selected,
  onPick,
  aside,
}: {
  rows: AlertRow[] | undefined;
  storeId?: string;
  emphasis?: string;
  selected?: { store: number; product: number } | null;
  onPick: (row: AlertRow) => void;
  aside: ReactNode;
}) {
  const [hovered, setHovered] = useState<AlertRow | null>(null);

  const wall = useMemo(() => {
    if (!rows?.length) return null;
    const stores = [...new Map(rows.map((r) => [r.store_id, r.store_name.split(",")[0]])).entries()].sort(
      (a, b) => a[0] - b[0],
    );
    const bays = new Map<string, Map<number, string>>();
    for (const r of rows) {
      if (!bays.has(r.category)) bays.set(r.category, new Map());
      bays.get(r.category)!.set(r.product_id, r.sku);
    }
    const categories = [...bays.entries()]
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([name, products]) => ({
        name,
        products: [...products.entries()].sort((a, b) => a[1].localeCompare(b[1])).map(([id]) => id),
      }));
    const lookup = new Map(rows.map((r) => [`${r.store_id}-${r.product_id}`, r]));
    return { stores, categories, lookup };
  }, [rows]);

  const worst = useMemo(() => {
    const scoped = (rows ?? []).filter(
      (r) => r.status === "stockout_risk" && (!storeId || String(r.store_id) === storeId),
    );
    return scoped.sort((a, b) => b.revenue_at_risk - a.revenue_at_risk)[0];
  }, [rows, storeId]);

  const shown = hovered ?? worst;

  return (
    <section className="grid grid-cols-[minmax(0,1fr)] gap-x-10 gap-y-5 rounded-lg bg-band p-5 text-band-ink sm:p-6 xl:grid-cols-[250px_minmax(0,1fr)]">
      <div className="min-w-0">{aside}</div>
      <div className="min-w-0">
        {!wall ? (
          <Bar className="h-52 w-full !bg-band-raised" />
        ) : (
          <>
            <div className="flex" aria-hidden>
              <span className="w-[76px] flex-none sm:w-[104px]" />
              <div className="flex min-w-0 flex-1 gap-1 sm:gap-1.5">
                {wall.categories.map((c) => (
                  <span
                    key={c.name}
                    className="min-w-0 truncate pb-1.5 text-xs text-band-muted"
                    style={{ flex: `${c.products.length} 1 0` }}
                  >
                    {SHORT_CATEGORY[c.name] ?? c.name}
                  </span>
                ))}
              </div>
            </div>
            <div className="grid gap-[3px]" onMouseLeave={() => setHovered(null)}>
              {wall.stores.map(([store, name]) => {
                const inScope = !storeId || String(store) === storeId;
                return (
                  <div key={store} className="flex items-center">
                    <span
                      className={clsx(
                        "w-[76px] flex-none truncate pr-2 text-xs sm:w-[104px] sm:text-[13px]",
                        inScope ? "text-band-ink" : "text-band-muted",
                      )}
                    >
                      {name}
                    </span>
                    <div className="flex min-w-0 flex-1 gap-1 sm:gap-1.5">
                      {wall.categories.map((c) => (
                        <div
                          key={c.name}
                          className="grid min-w-0 gap-px sm:gap-0.5"
                          style={{
                            flex: `${c.products.length} 1 0`,
                            gridTemplateColumns: `repeat(${c.products.length}, minmax(0, 1fr))`,
                          }}
                        >
                          {c.products.map((product) => {
                            const r = wall.lookup.get(`${store}-${product}`);
                            if (!r) return <span key={product} />;
                            const isSelected = selected?.store === store && selected?.product === product;
                            const faded = !inScope || (emphasis !== undefined && r.status !== emphasis);
                            return (
                              <button
                                key={product}
                                type="button"
                                // The tab order holds only the shelves that need a decision.
                                tabIndex={r.status === "stockout_risk" ? 0 : -1}
                                aria-label={describe(r)}
                                onClick={() => onPick(r)}
                                onMouseEnter={() => setHovered(r)}
                                onFocus={() => setHovered(r)}
                                className={clsx(
                                  "h-[15px] min-w-0 rounded-[2px] transition-opacity hover:outline hover:outline-1 hover:outline-offset-1 hover:outline-white sm:h-[18px]",
                                  isSelected && "outline outline-2 outline-offset-1 outline-white",
                                  faded && !isSelected && "opacity-30",
                                )}
                                style={{ background: SHELF_COLOUR[r.status] }}
                              />
                            );
                          })}
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
            <p className="mt-3 min-h-5 text-[13px] text-band-muted sm:pl-[104px]">
              {shown && (
                <>
                  <span className="text-band-ink">{shown === hovered ? "" : "First to act on: "}</span>
                  {describe(shown)}
                </>
              )}
            </p>
          </>
        )}
      </div>
    </section>
  );
}
