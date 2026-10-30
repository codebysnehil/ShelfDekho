import data from "./snapshot.json";
import type { AlertRow, Breakdown, ChartSpec, ForecastMetrics, Matrix, Summary, Trend } from "./api";

// Real figures exported from the dataset by `python -m app.jobs.snapshot`, so the
// landing page renders instantly even while the free-tier API is asleep.
export type Answer = {
  question: string;
  title: string;
  sql: string;
  columns: string[];
  rows: (string | number | null)[][];
  chart: ChartSpec;
  answer: string;
};

export type Snapshot = {
  as_of: string;
  safety_days: number;
  shelves: {
    counts: { stockout_risk: number; overstock: number; healthy: number };
    revenue_at_risk: number;
    rows: AlertRow[];
  };
  summary: Summary;
  trend: Trend;
  accuracy: ForecastMetrics;
  matrix: Matrix;
  by_category: Breakdown;
  by_store: Breakdown;
  answers: Answer[];
};

export const snapshot = data as unknown as Snapshot;

export function suggestedOrder(row: AlertRow, safetyDays: number, caseSize = 1): number {
  const need = row.daily_demand * (row.lead_time_days + safetyDays) - row.on_hand;
  return Math.max(0, Math.ceil(need / caseSize) * caseSize);
}
