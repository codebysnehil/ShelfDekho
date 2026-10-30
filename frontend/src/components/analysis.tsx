import clsx from "clsx";
import type { Matrix } from "@/lib/api";
import { formatInr } from "@/lib/format";

export function signedInr(value: number) {
  const body = formatInr(Math.abs(value), true);
  return value > 0 ? `+${body}` : value < 0 ? `−${body}` : body;
}

export function signedPct(v: number | null | undefined) {
  if (v === null || v === undefined) return "—";
  const rounded = Math.round(v);
  return `${rounded > 0 ? "+" : rounded < 0 ? "−" : ""}${Math.abs(rounded)}%`;
}

const SHORT_CATEGORY: Record<string, string> = {
  "Snacks & Beverages": "Snacks",
  "Personal Care": "Personal",
  "Home Care": "Home",
  "Festive & Gifting": "Festive",
};

/** Blue is well ahead of last year, red well behind; everything else stays blank. */
function heat(v: number | null | undefined) {
  if (v === null || v === undefined || Math.abs(v) < 10) return undefined;
  const strength = Math.min(Math.abs(v) / 40, 1) * 0.42 + 0.1;
  return `rgba(var(${v > 0 ? "--heat-up" : "--heat-down"}), ${strength})`;
}

/** Where the change in revenue came from, in rupees, on one zero line. */
export function MovedBars({ rows }: { rows: { name: string; delta: number }[] }) {
  const max = Math.max(...rows.map((r) => Math.abs(r.delta)), 1);
  return (
    <ul>
      {rows.map((r) => (
        <li
          key={r.name}
          className="grid h-[52px] grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)_72px] items-center gap-x-3 border-t border-rule first:border-t-0"
        >
          <span className="truncate">{r.name}</span>
          <div className="relative h-2.5">
            <span className="absolute -inset-y-1 left-1/2 w-px bg-line" />
            <span
              className={clsx("absolute inset-y-0 rounded-[3px]", r.delta < 0 ? "bg-negative" : "bg-hue")}
              style={
                r.delta < 0
                  ? { right: "50%", width: `${(Math.abs(r.delta) / max) * 50}%` }
                  : { left: "50%", width: `${(r.delta / max) * 50}%` }
              }
            />
          </div>
          <span className="num text-right">{signedInr(r.delta)}</span>
        </li>
      ))}
    </ul>
  );
}

/** ShelfDekho's map of the chain: revenue change for every store and category. */
export function SalesTable({
  matrix,
  selected,
  onSelect,
}: {
  matrix: Matrix;
  selected?: string;
  onSelect?: (storeId: string) => void;
}) {
  return (
    <table className="w-full min-w-[560px] border-separate border-spacing-0.5 text-[13px]">
      <thead className="text-muted">
        <tr>
          <th className="pb-1 text-left font-normal">Store</th>
          {matrix.categories.map((c) => (
            <th key={c} className="pb-1 text-right font-normal">
              {SHORT_CATEGORY[c] ?? c}
            </th>
          ))}
          <th className="pb-1 pl-3 text-right font-normal">All</th>
        </tr>
      </thead>
      <tbody>
        {matrix.rows.map((r) => {
          const name = r.store.split(",")[0];
          const id = String(r.store_id);
          return (
            <tr key={r.store_id} className={clsx(id === selected && "font-medium")}>
              <th scope="row" className="pr-3 text-left font-normal whitespace-nowrap">
                {onSelect ? (
                  <button onClick={() => onSelect(id === selected ? "" : id)} className="hover:underline">
                    {name}
                  </button>
                ) : (
                  name
                )}
              </th>
              {r.cells.map((c) => (
                <td
                  key={c.category}
                  className="num rounded-[5px] px-2 py-[9px] text-right"
                  style={{ background: heat(c.yoy_pct) }}
                  title={`${r.store}, ${c.category}: ${formatInr(c.revenue, true)}`}
                >
                  {signedPct(c.yoy_pct)}
                </td>
              ))}
              <td className="num pl-3 text-right font-medium">{signedPct(r.yoy_pct)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
