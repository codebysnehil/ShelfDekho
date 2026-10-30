"use client";

import { formatDate } from "@/lib/format";
import { LegendItem } from "./charts";

function addDays(iso: string, days: number) {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + Math.round(days));
  const pad = (n: number) => String(n).padStart(2, "0"); // taste-skill-ignore: ISO date, not a label
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/**
 * The shelf's next few weeks: stock falls at the forecast rate, a reorder placed today
 * lands after the lead time, and the gap in between is the time the shelf stands empty.
 */
export function StockRunway({
  asOf,
  onHand,
  dailyDemand,
  leadTime,
  order,
}: {
  asOf: string;
  onHand: number;
  dailyDemand: number;
  leadTime: number;
  order: number;
}) {
  if (dailyDemand <= 0.05) {
    return <p className="text-sm text-muted">No expected sales, so this shelf is not running down.</p>;
  }
  const cover = onHand / dailyDemand;
  const atArrival = Math.max(0, onHand - dailyDemand * leadTime) + order;
  const span = Math.max(leadTime + 14, Math.min(cover, 60) + 4);
  const top = Math.max(onHand, atArrival, 1) * 1.08;
  const W = 400;
  const H = 96;
  const x = (day: number) => (Math.min(day, span) / span) * W;
  const y = (units: number) => H - (Math.max(units, 0) / top) * H;
  const empty = cover < leadTime;
  const afterArrival = Math.max(0, atArrival - dailyDemand * (span - leadTime));
  const stockPath = empty
    ? `M0 ${y(onHand)} L${x(cover)} ${H} L${x(leadTime)} ${H}`
    : `M0 ${y(onHand)} L${x(leadTime)} ${y(onHand - dailyDemand * leadTime)}`;

  return (
    <figure>
      <div className="mb-1 flex flex-wrap gap-x-3">
        <LegendItem label="Stock" kind="line" color="var(--text)" />
        {order > 0 && <LegendItem label="After this order" kind="dash" color="var(--hue)" />}
        {empty && <LegendItem label="Shelf empty" kind="span" color="var(--negative)" />}
      </div>
      <svg viewBox={`0 0 ${W} ${H + 1}`} className="block h-24 w-full" preserveAspectRatio="none" role="img"
        aria-label={`Stock falls from ${onHand} units; a reorder arrives in ${leadTime} days`}>
        {empty && (
          <rect x={x(cover)} y={0} width={x(leadTime) - x(cover)} height={H} fill="var(--negative)" opacity={0.14} />
        )}
        <line x1={0} y1={H} x2={W} y2={H} stroke="var(--text)" strokeWidth={1} vectorEffect="non-scaling-stroke" />
        <path d={stockPath} fill="none" stroke="var(--text)" strokeWidth={2} vectorEffect="non-scaling-stroke" />
        {order > 0 && (
          <path
            d={`M${x(leadTime)} ${empty ? H : y(onHand - dailyDemand * leadTime)} L${x(leadTime)} ${y(atArrival)} L${W} ${y(afterArrival)}`}
            fill="none"
            stroke="var(--hue)"
            strokeWidth={2}
            strokeDasharray="5 3"
            vectorEffect="non-scaling-stroke"
          />
        )}
      </svg>
      <figcaption className="mt-1.5 text-[13px]">
        {empty ? (
          <>
            Empties <span className="font-medium">{formatDate(addDays(asOf, cover))}</span>. An order placed
            today lands <span className="font-medium">{formatDate(addDays(asOf, leadTime))}</span>, so the shelf
            stands empty for about{" "}
            <span className="font-medium text-negative">{Math.round(leadTime - cover)} days</span>.
          </>
        ) : (
          <>
            Lasts until about <span className="font-medium">{formatDate(addDays(asOf, cover))}</span>, past the{" "}
            {leadTime}-day reorder time.
          </>
        )}
      </figcaption>
    </figure>
  );
}
