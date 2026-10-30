"use client";

import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ChartSpec, ForecastSeries, Trend } from "@/lib/api";
import { formatCell, formatDate, formatInr, formatNumber, humanize, isMoneyColumn } from "@/lib/format";

// Ledger chart rules: one hue on the main series, ink or grey for the rest, 3-5 faint
// horizontal gridlines, no y-axis line, ticks on the right at round values above the max,
// straight segments, no point markers, flat x labels.
const HUE = "var(--hue)";
const INK = "var(--text)";
const GREY = "var(--comparison)";
const TICK = { fill: "var(--muted)", fontSize: 12 };
const MAIN_SERIES = [HUE, INK, GREY];

/** Round, even ticks from zero with the top tick above the maximum. */
export function niceTicks(max: number, count = 4): number[] {
  if (!(max > 0)) return [0, 1];
  const raw = max / count;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= raw) ?? raw;
  const top = Math.ceil((max * 1.04) / step) * step;
  return Array.from({ length: Math.round(top / step) + 1 }, (_, i) => +(i * step).toFixed(6));
}

/**
 * Ticks for a line that barely moves: start at a round floor so the movement can be seen.
 * Bars keep niceTicks, which always starts at zero.
 */
export function lineTicks(min: number, max: number, count = 4): number[] {
  if (!(max > 0) || min < max * 0.4) return niceTicks(max, count);
  const raw = (max - min) / count;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= raw) ?? raw;
  const floor = Math.floor(min / step) * step;
  const top = Math.ceil((max * 1.01) / step) * step;
  return Array.from({ length: Math.round((top - floor) / step) + 1 }, (_, i) => +(floor + i * step).toFixed(6));
}

/** A band needs two edges on a category axis: from this week to its neighbour. */
function weekBand(weeks: string[], week: string): [string, string] {
  const i = weeks.indexOf(week);
  return i < weeks.length - 1 ? [week, weeks[i + 1]] : [weeks[Math.max(i - 1, 0)], week];
}

type TipRow = { name?: string | number; value?: unknown; color?: string; dataKey?: unknown };

function Tip({
  active,
  label,
  payload,
  formatLabel,
  formatValue,
}: {
  active?: boolean;
  label?: string | number;
  payload?: TipRow[];
  formatLabel?: (label: string) => string;
  formatValue: (key: string, value: number) => string;
}) {
  if (!active || !payload?.length) return null;
  const rows = payload.filter(
    (p) => p.value !== null && p.value !== undefined && !Array.isArray(p.value),
  );
  return (
    // taste-skill-ignore: tooltips float, so they may cast a shadow
    <div className="rounded-md border border-line bg-surface px-2.5 py-1.5 text-xs shadow-md">
      <p className="mb-0.5 text-muted">{formatLabel ? formatLabel(String(label)) : label}</p>
      {rows.map((p) => (
        <p key={String(p.dataKey)} className="flex items-center gap-2">
          <span className="text-muted">{p.name}</span>
          <span className="num ml-auto pl-3 font-medium">
            {formatValue(String(p.dataKey), Number(p.value))}
          </span>
        </p>
      ))}
    </div>
  );
}

/** Legend entries for a card header; each swatch is the mark it explains. */
export function LegendItem({
  label,
  kind,
  color,
}: {
  label: string;
  kind: "line" | "dash" | "band" | "span";
  color: string;
}) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-muted">
      <svg width="16" height="8" aria-hidden>
        {kind === "line" && <line x1="0" y1="4" x2="16" y2="4" stroke={color} strokeWidth="2" />}
        {kind === "dash" && (
          <line x1="0" y1="4" x2="16" y2="4" stroke={color} strokeWidth="2" strokeDasharray="4 3" />
        )}
        {kind === "band" && <rect width="16" height="8" fill={color} opacity="0.15" />}
        {kind === "span" && <rect width="16" height="8" fill={color} opacity="0.1" />}
      </svg>
      {label}
    </span>
  );
}

export type Metric = "revenue" | "units" | "margin_pct" | "promo_pct";

const METRICS: Record<
  Metric,
  { now: keyof Trend["points"][number]; before: keyof Trend["points"][number]; format: (v: number) => string }
> = {
  revenue: { now: "revenue", before: "revenue_ly", format: (v) => formatInr(v, true) },
  units: { now: "units", before: "units_ly", format: (v) => formatNumber(v, true) },
  margin_pct: { now: "margin_pct", before: "margin_pct_ly", format: (v) => `${v.toFixed(1)}%` },
  promo_pct: { now: "promo_pct", before: "promo_pct_ly", format: (v) => `${v.toFixed(0)}%` },
};

export function MetricChart({
  trend,
  metric = "revenue",
  height = 240,
}: {
  trend: Trend;
  metric?: Metric;
  height?: number;
}) {
  const m = METRICS[metric];
  const values = trend.points.flatMap((p) => {
    const before = p[m.before];
    return [Number(p[m.now]), ...(before === null || before === undefined ? [] : [Number(before)])];
  });
  const ticks = lineTicks(Math.min(...values), Math.max(...values));
  const weeks = trend.points.map((p) => p.week_start);
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={trend.points} margin={{ top: 22, right: 0, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="metric-fade" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--hue)" stopOpacity={0.2} />
            <stop offset="100%" stopColor="var(--hue)" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="var(--grid)" vertical={false} />
        {(trend.events ?? []).map((e) => (
          <ReferenceArea
            key={e.week_start}
            x1={weekBand(weeks, e.week_start)[0]}
            x2={weekBand(weeks, e.week_start)[1]}
            fill="var(--text)"
            fillOpacity={0.08}
            stroke="none"
            label={{
              value: e.label,
              position: "insideTopRight",
              fill: "var(--text)",
              fontSize: 12,
              dy: -20,
            }}
          />
        ))}
        <XAxis
          dataKey="week_start"
          tick={TICK}
          tickLine={false}
          axisLine={{ stroke: "var(--control)", strokeWidth: 1 }}
          tickFormatter={(d: string) => formatDate(d)}
          minTickGap={48}
          padding={{ left: 4, right: 4 }}
        />
        <YAxis
          orientation="right"
          ticks={ticks}
          domain={[ticks[0], ticks[ticks.length - 1]]}
          tick={TICK}
          tickLine={false}
          axisLine={false}
          width={60}
          tickFormatter={m.format}
        />
        <Tooltip
          cursor={{ stroke: "var(--control)" }}
          content={
            <Tip
              formatLabel={(d) => `Week of ${formatDate(d, { year: "numeric" })}`}
              formatValue={(_, v) => m.format(v)}
            />
          }
        />
        <Line
          name="Same week last year"
          dataKey={m.before}
          stroke={GREY}
          strokeWidth={1.5}
          dot={false}
          isAnimationActive={false}
        />
        <Area
          name="This year"
          dataKey={m.now}
          baseValue={ticks[0]}
          stroke={HUE}
          strokeWidth={2.5}
          fill="url(#metric-fade)"
          dot={false}
          activeDot={{ r: 4, fill: HUE, stroke: "var(--surface)", strokeWidth: 2 }}
          isAnimationActive={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export function ForecastChart({ series, height = 240 }: { series: ForecastSeries; height?: number }) {
  const data = series.points.map((p) => ({
    ...p,
    band: p.lower !== null && p.upper !== null ? [p.lower, p.upper] : null,
  }));
  // A forecast is not a fact: join it to the last actual week, then dash it.
  const lastActual = [...data].reverse().find((p) => p.actual !== null);
  if (lastActual) lastActual.forecast = lastActual.actual;
  const today = lastActual?.week_start;
  const last = data[data.length - 1];
  const max = Math.max(...data.map((p) => Math.max(p.actual ?? 0, p.upper ?? 0, p.forecast ?? 0)));
  const ticks = niceTicks(max);

  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 22, right: 0, left: 0, bottom: 0 }}>
        <CartesianGrid stroke="var(--grid)" vertical={false} />
        {data
          .filter((p) => p.on_promo)
          .map((p) => (
            <ReferenceArea
              key={p.week_start}
              x1={weekBand(data.map((d) => d.week_start), p.week_start)[0]}
              x2={weekBand(data.map((d) => d.week_start), p.week_start)[1]}
              fill="var(--text)"
              fillOpacity={0.08}
              stroke="none"
            />
          ))}
        {today && (
          <ReferenceLine
            x={today}
            stroke="var(--text)"
            strokeWidth={1}
            label={{ value: "Today", position: "insideTopLeft", fill: "var(--text)", fontSize: 12, dy: -20 }}
          />
        )}
        <XAxis
          dataKey="week_start"
          tick={TICK}
          tickLine={false}
          axisLine={{ stroke: "var(--text)", strokeWidth: 1 }}
          tickFormatter={(d: string) => formatDate(d)}
          minTickGap={40}
          padding={{ left: 4, right: 4 }}
        />
        <YAxis
          orientation="right"
          ticks={ticks}
          domain={[0, ticks[ticks.length - 1]]}
          tick={TICK}
          tickLine={false}
          axisLine={false}
          width={40}
          allowDecimals={false}
        />
        <Tooltip
          cursor={{ stroke: "var(--control)" }}
          content={
            <Tip
              formatLabel={(d) => `Week of ${formatDate(d, { year: "numeric" })}`}
              formatValue={(_, v) => `${Math.round(v).toLocaleString("en-IN")} units`}
            />
          }
        />
        <Area
          name="80% range"
          dataKey="band"
          stroke="none"
          fill={HUE}
          fillOpacity={0.12}
          isAnimationActive={false}
        />
        <Line
          name="Sold"
          dataKey="actual"
          stroke={INK}
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
        />
        <Line
          name="Forecast"
          dataKey="forecast"
          stroke={HUE}
          strokeWidth={2}
          strokeDasharray="5 3"
          dot={false}
          isAnimationActive={false}
          label={(props: { index?: number; x?: number | string; y?: number | string }) =>
            props.index === data.length - 1 && last.forecast !== null ? (
              <text
                key="end"
                x={Number(props.x ?? 0) - 4}
                y={Number(props.y ?? 0) - 8}
                textAnchor="end"
                fontSize={12}
                fill="var(--text)"
              >
                {Math.round(last.forecast)} units
              </text>
            ) : (
              <g key={props.index} />
            )
          }
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

/** Chart for an AI analyst result, driven by the spec the backend inferred. */
export function ResultChart({
  spec,
  columns,
  rows,
}: {
  spec: ChartSpec;
  columns: string[];
  rows: (string | number | null)[][];
}) {
  if (spec.type === "table" || !spec.x || !spec.y?.length) return null;
  const data = rows.map((r) => Object.fromEntries(columns.map((c, i) => [c, r[i]])));
  const y = spec.y.slice(0, 3);
  const x = spec.x;
  const isDate =
    typeof data[0]?.[x] === "string" && /^\d{4}-\d{2}-\d{2}/.test(String(data[0][x]));
  const money = y.every(isMoneyColumn);
  const values = data.flatMap((d) => y.map((k) => Number(d[k]) || 0));
  const max = Math.max(...values, 0);
  const min = Math.min(...values, 0);
  const tickY = (v: number) => (money ? formatInr(v, true) : v.toLocaleString("en-IN"));
  const tip = (
    <Tip
      formatLabel={(l) => (isDate ? formatDate(l, { year: "numeric" }) : l)}
      formatValue={(key, v) => formatCell(key, v)}
    />
  );
  // The comparison series is always grey, so "this" and "last year" read apart.
  const seriesColor = (key: string, i: number) =>
    /last_year|_ly$|normal|previous/.test(key) ? GREY : MAIN_SERIES[i];
  const legend =
    y.length > 1 ? (
      <div className="mb-2 flex flex-wrap gap-x-4 gap-y-1">
        {y.map((k, i) => (
          <LegendItem key={k} label={humanize(k)} kind="line" color={seriesColor(k, i)} />
        ))}
      </div>
    ) : null;

  if (spec.type === "line") {
    const ticks = min < 0 ? undefined : lineTicks(Math.min(...values), max);
    return (
      <div>
        {legend}
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={data} margin={{ top: 8, right: 0, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="var(--grid)" vertical={false} />
            <XAxis
              dataKey={x}
              tick={TICK}
              tickLine={false}
              axisLine={{ stroke: "var(--text)" }}
              tickFormatter={(v: string) => (isDate ? formatDate(v) : String(v))}
              minTickGap={40}
            />
            <YAxis
              orientation="right"
              ticks={ticks}
              domain={ticks ? [ticks[0], ticks[ticks.length - 1]] : ["auto", "auto"]}
              tick={TICK}
              tickLine={false}
              axisLine={false}
              width={64}
              tickFormatter={tickY}
            />
            <Tooltip content={tip} cursor={{ stroke: "var(--control)" }} />
            {y.map((key, i) => (
              <Line
                key={key}
                name={humanize(key)}
                dataKey={key}
                stroke={seriesColor(key, i)}
                strokeWidth={i === 0 ? 2 : 1.5}
                dot={false}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    );
  }

  // Bars: horizontal with labels in a lane on the left, so long names never rotate.
  const ticks = min < 0 ? undefined : niceTicks(max);
  return (
    <div>
      {legend}
      <ResponsiveContainer width="100%" height={Math.max(140, data.length * (y.length > 1 ? 44 : 32) + 32)}>
        <BarChart data={data} layout="vertical" margin={{ top: 0, right: 8, left: 0, bottom: 0 }} barGap={2}>
          <CartesianGrid stroke="var(--grid)" horizontal={false} />
          <XAxis
            type="number"
            ticks={ticks}
            domain={ticks ? [0, ticks[ticks.length - 1]] : ["auto", "auto"]}
            tick={TICK}
            tickLine={false}
            axisLine={false}
            tickFormatter={tickY}
          />
          <YAxis
            type="category"
            dataKey={x}
            width={170}
            tick={{ fill: "var(--text)", fontSize: 13 }}
            tickLine={false}
            axisLine={{ stroke: "var(--text)" }}
            tickFormatter={(v: string) => (String(v).length > 24 ? `${String(v).slice(0, 23)}…` : v)}
          />
          <Tooltip content={tip} cursor={{ fill: "var(--raised)", opacity: 0.6 }} />
          {y.map((key, i) => (
            <Bar
              key={key}
              name={humanize(key)}
              dataKey={key}
              fill={seriesColor(key, i)}
              radius={[0, 3, 3, 0]}
              barSize={y.length > 1 ? 14 : 18}
              isAnimationActive={false}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
