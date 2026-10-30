"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Loader2, Send } from "lucide-react";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { TitleRow } from "@/components/app-shell";
import { ResultChart } from "@/components/charts";
import { Bar, Button, Segmented } from "@/components/ui";
import {
  type AnalystEvent,
  ApiError,
  api,
  askAnalyst,
  type ChartSpec,
  type Quota,
  type Suggestions,
} from "@/lib/api";
import { formatCell, humanize } from "@/lib/format";

type Turn = {
  id: number;
  question: string;
  status: string | null;
  table?: { columns: string[]; rows: (string | number | null)[][]; truncated: boolean };
  chart?: { spec: ChartSpec; title: string };
  answer: string;
  error?: string;
};

function reduce(turn: Turn, event: AnalystEvent): Turn {
  switch (event.type) {
    case "status":
      return { ...turn, status: event.message };
    case "sql":
      return turn;
    case "table":
      return {
        ...turn,
        table: {
          ...event,
          rows: event.rows.map((row) =>
            row.map((v: unknown) =>
              typeof v === "boolean" ? (v ? "Yes" : "No") : (v as string | number | null),
            ),
          ),
        },
      };
    case "chart":
      return { ...turn, chart: { spec: event.chart, title: event.title } };
    case "answer":
      return { ...turn, answer: turn.answer + event.delta };
    case "error":
      return { ...turn, error: event.message, status: null };
    case "done":
      return { ...turn, status: null };
  }
}

/** A workspace, not a chat: questions on the left, one worked answer filling the right. */
export default function AnalystPage() {
  const queryClient = useQueryClient();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const nextId = useRef(0);
  const opened = useRef(false);

  const suggestions = useQuery({
    queryKey: ["suggestions"],
    queryFn: () => api<Suggestions>("/api/analyst/suggestions"),
  });
  const quota = useQuery({
    queryKey: ["quota"],
    queryFn: () => api<Quota>("/api/analyst/quota"),
    staleTime: 0,
  });
  const list = suggestions.data?.suggestions;
  const q = quota.data;

  async function ask(question: string) {
    const text = question.trim();
    if (!text || busy) return;
    const existing = turns.find((t) => t.question === text);
    if (existing) {
      setActiveId(existing.id);
      return;
    }
    const id = ++nextId.current;
    setInput("");
    setBusy(true);
    setTurns((t) => [...t, { id, question: text, status: "Thinking", answer: "" }]);
    setActiveId(id);
    const update = (fn: (turn: Turn) => Turn) =>
      setTurns((all) => all.map((turn) => (turn.id === id ? fn(turn) : turn)));
    try {
      for await (const event of askAnalyst(text)) update((turn) => reduce(turn, event));
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "That didn't go through. Please try again.";
      update((turn) => ({ ...turn, status: null, error: message }));
    } finally {
      setBusy(false);
      queryClient.invalidateQueries({ queryKey: ["quota"] });
    }
  }

  // Open on a worked answer, so the screen shows what it does. Listed questions do not use up the daily allowance.
  useEffect(() => {
    if (list?.length && !opened.current) {
      opened.current = true;
      void ask(list[1]?.question ?? list[0].question);
    }
  });

  const active = turns.find((t) => t.id === activeId);
  const asked = turns.filter((t) => !list?.some((s) => s.question === t.question));

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    ask(input);
  }

  return (
    <>
      <TitleRow
        title="Analyst"
        finding="Ask about sales, stores, promotions or stock, and get the answer with the numbers behind it."
      />

      <div className="grid items-start gap-x-8 gap-y-6 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-4">
          <div>
            <form
              onSubmit={onSubmit}
              className="flex items-center gap-2 rounded-lg bg-band p-2.5 focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-hue"
            >
              <label htmlFor="question" className="sr-only">
                Your question
              </label>
              <input
                id="question"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                maxLength={300}
                placeholder="Which category had the best margin last month?"
                className="h-10 min-w-0 flex-1 bg-transparent px-2.5 font-voice text-[17px] text-band-ink placeholder:text-band-muted focus:outline-none"
              />
              <Button
                type="submit"
                className="!bg-band-ink !text-band hover:!bg-white"
                disabled={busy || input.trim().length < 3}
              >
                {busy ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <Send className="size-4" aria-hidden />}
                Ask
              </Button>
            </form>
            <p className="num mt-1.5 min-h-5 px-1 text-[13px] text-muted">
              {q
                ? q.llm_configured
                  ? `${q.remaining_today} of ${q.limit_per_day} questions of your own left today`
                  : "Asking your own questions is switched off in this demo. The listed questions always work."
                : ""}
            </p>
          </div>
          {active ? <Answer key={active.id} turn={active} /> : <AnswerLoading />}
        </div>

        <aside>
          <h2 className="px-3 pb-1.5 text-[15px] font-semibold">Try asking</h2>
          <ul>
            {(list ?? Array.from({ length: 6 }, () => null)).map((s, i) => (
              <li key={s?.question ?? i}>
                {s ? (
                  <QuestionButton
                    text={s.question}
                    active={active?.question === s.question}
                    disabled={busy}
                    onClick={() => ask(s.question)}
                  />
                ) : (
                  <Bar className="m-3 h-9" />
                )}
              </li>
            ))}
          </ul>
          {asked.length > 0 && (
            <>
              <h3 className="px-3 pt-4 pb-1.5 text-[15px] font-semibold">You asked</h3>
              <ul>
                {asked.map((t) => (
                  <li key={t.id}>
                    <QuestionButton
                      text={t.question}
                      active={t.id === activeId}
                      disabled={busy}
                      onClick={() => setActiveId(t.id)}
                    />
                  </li>
                ))}
              </ul>
            </>
          )}
        </aside>
      </div>
    </>
  );
}

function QuestionButton({
  text,
  active,
  disabled,
  onClick,
}: {
  text: string;
  active: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled && !active}
      aria-current={active ? "true" : undefined}
      className={clsx(
        "block w-full rounded-md px-3 py-2.5 text-left text-sm transition-colors disabled:opacity-60",
        active ? "bg-active font-medium text-active-ink" : "hover:bg-raised",
      )}
    >
      <span className="block leading-snug">{text}</span>
    </button>
  );
}

function AnswerLoading() {
  return (
    <section className="rounded-lg border border-line bg-surface p-6">
      <Bar className="h-5 w-2/3" />
      <Bar className="mt-4 h-16 w-full" />
      <Bar className="mt-6 h-[240px] w-full" />
    </section>
  );
}

type View = "chart" | "table";

function Answer({ turn }: { turn: Turn }) {
  const hasChart = turn.chart && turn.chart.spec.type !== "table";
  const [picked, setPicked] = useState<View | null>(null);
  const view: View = picked ?? (hasChart ? "chart" : "table");
  const views: { value: View; label: string }[] = [
    ...(hasChart ? [{ value: "chart" as View, label: "Chart" }] : []),
    { value: "table", label: "Table" },
  ];

  return (
    <article className="rounded-lg border border-line bg-surface">
      <div className="px-6 pt-6">
        <h2 className="text-sm text-muted">{turn.question}</h2>
        {turn.status && (
          <p className="mt-2 flex items-center gap-2 text-sm text-muted" role="status">
            <Loader2 className="size-3.5 animate-spin" aria-hidden /> {turn.status}…
          </p>
        )}
        {turn.error && <p className="mt-2 text-negative">{turn.error}</p>}
        {turn.answer && <p className="mt-2 max-w-[62ch] font-voice text-[21px] leading-[1.5] tracking-[-0.005em]">{turn.answer}</p>}
      </div>

      {turn.table && (
        <div className="mt-5 border-t border-rule px-6 pt-4 pb-5">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm text-muted">{view === "chart" ? turn.chart?.title : "The numbers"}</p>
            {views.length > 1 && (
              <Segmented label="Show as" value={view} onChange={setPicked} options={views} small />
            )}
          </div>
          {view === "chart" && turn.chart && turn.table && (
            <ResultChart spec={turn.chart.spec} columns={turn.table.columns} rows={turn.table.rows} />
          )}
          {view === "table" && turn.table && <ResultTable table={turn.table} />}
        </div>
      )}
    </article>
  );
}

function ResultTable({ table }: { table: NonNullable<Turn["table"]> }) {
  // Database ids mean nothing to the reader.
  const shown = table.columns.flatMap((c, j) => (/(^|_)id$/i.test(c) ? [] : [j]));
  return (
    <div className="max-h-96 overflow-auto">
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-surface text-xs text-muted">
          <tr>
            {shown.map((j) => (
              <th
                key={table.columns[j]}
                className={clsx(
                  "py-2 pr-4 font-normal whitespace-nowrap",
                  typeof table.rows[0]?.[j] === "number" ? "text-right" : "text-left",
                )}
              >
                {humanize(table.columns[j])}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, i) => (
            <tr key={i} className="border-t border-rule">
              {shown.map((j) => (
                <td
                  key={j}
                  className={clsx("py-1.5 pr-4 whitespace-nowrap", typeof row[j] === "number" && "num text-right")}
                >
                  {formatCell(table.columns[j], row[j])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {table.truncated && (
        <p className="py-2 text-xs text-muted">Showing the first {table.rows.length} rows.</p>
      )}
    </div>
  );
}
