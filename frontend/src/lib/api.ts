import type { components } from "./api-types";

// Types come from the backend's OpenAPI schema (`npm run gen:types`), so the
// frontend cannot drift from the API contract silently.
type Schemas = components["schemas"];
export type Summary = Schemas["SummaryResponse"];
export type Kpi = Schemas["Kpi"];
export type Insight = Schemas["Insight"];
export type Trend = Schemas["TrendResponse"];
export type Breakdown = Schemas["BreakdownResponse"];
export type Products = Schemas["ProductsResponse"];
export type Store = Schemas["StoreOut"];
export type Product = Schemas["ProductOut"];
export type ForecastMetrics = Schemas["ForecastMetrics"];
export type ForecastSeries = Schemas["ForecastSeries"];
export type Alerts = Schemas["AlertsResponse"];
export type AlertRow = Schemas["AlertRow"];
export type Quota = Schemas["Quota"];
export type Matrix = Schemas["MatrixResponse"];
export type Upcoming = Schemas["UpcomingResponse"];
export type Suggestions = Schemas["SuggestionsResponse"];
export type Token = Schemas["TokenResponse"];
export type DataStatus = Schemas["DataStatus"];
export type ImportReport = Schemas["ImportReport"];

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(
  /\/$/,
  "",
);

const TOKEN_KEY = "shelfdekho.token";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function clearToken() {
  try {
    localStorage.removeItem(TOKEN_KEY);
  } catch {}
}

export async function demoLogin(): Promise<Token> {
  const res = await fetch(`${API_URL}/api/auth/demo`, { method: "POST" });
  if (!res.ok) throw new ApiError(res.status, "Could not open the demo");
  const token = (await res.json()) as Token;
  try {
    localStorage.setItem(TOKEN_KEY, token.access_token);
  } catch {}
  return token;
}

let pendingSession: Promise<void> | null = null;

/**
 * Resolve once a demo token exists, signing in if needed. A sleeping free-tier server
 * can take up to a minute to answer, so sign-in retries for a while before giving up.
 */
export function ensureSession(): Promise<void> {
  if (getToken()) return Promise.resolve();
  pendingSession ??= (async () => {
    for (let attempt = 0; ; attempt++) {
      try {
        await demoLogin();
        return;
      } catch (err) {
        if (attempt >= 20) throw err;
        await new Promise((r) => setTimeout(r, 3000));
      }
    }
  })().finally(() => {
    pendingSession = null;
  });
  return pendingSession;
}

async function errorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json();
    return typeof body.detail === "string" ? body.detail : res.statusText;
  } catch {
    return res.statusText;
  }
}

type Params = Record<string, string | number | null | undefined>;

export async function api<T>(path: string, params?: Params): Promise<T> {
  const url = new URL(`${API_URL}${path}`);
  for (const [k, v] of Object.entries(params ?? {})) {
    if (v !== null && v !== undefined && v !== "") url.searchParams.set(k, String(v));
  }
  const send = async () => {
    await ensureSession();
    return fetch(url, { headers: { Authorization: `Bearer ${getToken() ?? ""}` } });
  };
  let res = await send();
  if (res.status === 401) {
    // Demo tokens expire after a day: start a fresh session and retry once.
    clearToken();
    res = await send();
  }
  if (!res.ok) throw new ApiError(res.status, await errorMessage(res));
  return res.json() as Promise<T>;
}

/** Send a CSV to be checked or added. */
export async function sendFile<T>(path: string, kind: string, file: File): Promise<T> {
  const url = new URL(`${API_URL}${path}`);
  url.searchParams.set("kind", kind);
  url.searchParams.set("filename", file.name.slice(0, 200));
  await ensureSession();
  const res = await fetch(url, {
    method: "POST",
    headers: { Authorization: `Bearer ${getToken() ?? ""}`, "Content-Type": "text/csv" },
    body: file,
  });
  if (!res.ok) throw new ApiError(res.status, await errorMessage(res));
  return res.json() as Promise<T>;
}

export async function fetchSample(kind: string): Promise<string> {
  await ensureSession();
  const res = await fetch(`${API_URL}/api/data/sample/${kind}`, {
    headers: { Authorization: `Bearer ${getToken() ?? ""}` },
  });
  if (!res.ok) throw new ApiError(res.status, await errorMessage(res));
  return res.text();
}

/** Ping the API so a sleeping free-tier server starts waking up immediately. */
export async function wakeServer(signal?: AbortSignal): Promise<boolean> {
  try {
    const res = await fetch(`${API_URL}/health`, { signal, cache: "no-store" });
    return res.ok;
  } catch {
    return false;
  }
}

// --- AI analyst stream -----------------------------------------------------------

export type ChartSpec = { type: "line" | "bar" | "table"; x?: string; y?: string[] };

export type AnalystEvent =
  | { type: "status"; message: string }
  | { type: "sql"; sql: string }
  | { type: "table"; columns: string[]; rows: (string | number | null)[][]; truncated: boolean }
  | { type: "chart"; chart: ChartSpec; title: string }
  | { type: "answer"; delta: string }
  | { type: "error"; message: string }
  | {
      type: "done";
      cached: boolean;
      provider: string | null;
      remaining: number | null;
      latency_ms: number;
    };

/** POST a question and yield server-sent events as they arrive. */
export async function* askAnalyst(
  question: string,
  signal?: AbortSignal,
): AsyncGenerator<AnalystEvent> {
  await ensureSession();
  const res = await fetch(`${API_URL}/api/analyst/ask`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${getToken() ?? ""}`,
    },
    body: JSON.stringify({ question }),
    signal,
  });
  if (!res.ok || !res.body) throw new ApiError(res.status, await errorMessage(res));

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    let boundary: number;
    while ((boundary = buffer.indexOf("\n\n")) >= 0) {
      const chunk = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const data = chunk
        .split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trim())
        .join("");
      if (data) yield JSON.parse(data) as AnalystEvent;
    }
  }
}
