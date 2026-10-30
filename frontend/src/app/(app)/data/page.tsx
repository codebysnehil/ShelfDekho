"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Download, FileUp, Loader2 } from "lucide-react";
import { type DragEvent, useRef, useState } from "react";
import { TitleRow } from "@/components/app-shell";
import { Bar, BlockError, Button, Panel, Segmented } from "@/components/ui";
import {
  api,
  ApiError,
  type DataStatus,
  fetchSample,
  type ImportReport,
  sendFile,
} from "@/lib/api";
import { formatDate, formatNumber } from "@/lib/format";

type Kind = "sales" | "stock";

const KINDS: Record<Kind, { label: string; needs: string; extra: string; outcome: string }> = {
  sales: {
    label: "Daily sales",
    needs: "date, store, sku, units",
    extra: "Revenue and discount are optional. Without revenue, it is worked out from your price.",
    outcome: "Forecasts are recalculated, and stock moves down by what sold since the last count.",
  },
  stock: {
    label: "Stock count",
    needs: "store, sku, on_hand",
    extra: "Date is optional. Without it, the count is taken as today's.",
    outcome: "Stock and every reorder suggestion are updated to this count.",
  },
};

const SAMPLE: Record<Kind, { columns: string[]; rows: string[][] }> = {
  sales: {
    columns: ["date", "store", "sku", "units"],
    rows: [
      ["2026-10-26", "DEL01", "DRY-001", "42"],
      ["2026-10-26", "DEL01", "SNB-007", "18"],
      ["2026-10-26", "MUM01", "DRY-001", "37"],
    ],
  },
  stock: {
    columns: ["store", "sku", "on_hand"],
    rows: [
      ["DEL01", "DRY-001", "480"],
      ["DEL01", "SNB-007", "151"],
      ["MUM01", "DRY-001", "392"],
    ],
  },
};

export default function DataPage() {
  const queryClient = useQueryClient();
  const [kind, setKind] = useState<Kind>("sales");
  const [file, setFile] = useState<File | null>(null);
  const [report, setReport] = useState<ImportReport | null>(null);
  const [busy, setBusy] = useState<"checking" | "adding" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [added, setAdded] = useState<string | null>(null);
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const status = useQuery({
    queryKey: ["data-status"],
    queryFn: () => api<DataStatus>("/api/data/status"),
  });
  const s = status.data;

  function start() {
    setFile(null);
    setReport(null);
    setError(null);
    if (input.current) input.current.value = "";
  }

  function problemText(err: unknown) {
    return err instanceof ApiError ? err.message : "That didn't go through. Please try again.";
  }

  async function check(next: File, forKind: Kind = kind) {
    setFile(next);
    setReport(null);
    setError(null);
    setAdded(null);
    setBusy("checking");
    try {
      setReport(await sendFile<ImportReport>("/api/data/check", forKind, next));
    } catch (err) {
      setError(problemText(err));
    } finally {
      setBusy(null);
    }
  }

  async function add() {
    if (!file || !report) return;
    setBusy("adding");
    setError(null);
    try {
      await sendFile("/api/data/import", kind, file);
      setAdded(
        `Added ${formatNumber(report.rows_ok)} ${report.rows_ok === 1 ? "row" : "rows"} from ${file.name}. Every screen now shows the new figures.`,
      );
      start();
      // Everything on every screen may have changed.
      await queryClient.invalidateQueries();
    } catch (err) {
      setError(problemText(err));
    } finally {
      setBusy(null);
    }
  }

  async function downloadSample() {
    const text = await fetchSample(kind);
    const url = URL.createObjectURL(new Blob([text], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `shelfiq-sample-${kind}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setOver(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped && !busy) void check(dropped);
  }

  return (
    <>
      <TitleRow
        title="Data"
        finding="Bring in each day's sales or a stock count. Every screen updates once a file is added."
      />

      <section className="mb-4 grid grid-cols-2 gap-x-8 gap-y-4 rounded-lg bg-band p-5 text-band-ink sm:p-6 lg:grid-cols-4">
        {[
          ["Sales run to", s?.sales_to ? formatDate(s.sales_to, { year: "numeric" }) : s ? "—" : null],
          ["Stock counted to", s?.stock_to ? formatDate(s.stock_to, { year: "numeric" }) : s ? "—" : null],
          ["Files added", s ? formatNumber(s.history.length) : null],
          ["Adding figures", s ? (s.can_add ? "On" : "Off in this demo") : null],
        ].map(([label, value]) => (
          <div key={label} className="min-w-0">
            <p className="text-[13px] text-band-muted">{label}</p>
            {value ? (
              <p className="num mt-0.5 font-voice text-[24px] leading-8 font-medium tracking-[-0.015em]">{value}</p>
            ) : (
              <Bar className="mt-1 h-7 w-32 !bg-band-raised" />
            )}
          </div>
        ))}
      </section>

      <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
        <Panel
          title="Add new figures"
          action={
            <Segmented
              label="What is in the file"
              value={kind}
              small
              onChange={(k: Kind) => {
                setKind(k);
                start();
                setAdded(null);
              }}
              options={[
                { value: "sales", label: KINDS.sales.label },
                { value: "stock", label: KINDS.stock.label },
              ]}
            />
          }
        >
          {added && (
            <p role="status" className="mb-3 rounded-md bg-pill-positive-bg px-3 py-2 text-sm text-pill-positive-ink">
              {added}
            </p>
          )}

          {!report ? (
            <label
              onDragOver={(e) => {
                e.preventDefault();
                setOver(true);
              }}
              onDragLeave={() => setOver(false)}
              onDrop={onDrop}
              className={clsx(
                "flex min-h-64 cursor-pointer flex-col items-center justify-center gap-2 rounded-md border-2 border-dashed px-6 py-8 text-center transition-colors focus-within:outline-2 focus-within:outline-hue",
                over ? "border-hue bg-active" : "border-control hover:border-hue hover:bg-hover",
              )}
            >
              {busy === "checking" ? (
                <>
                  <Loader2 className="size-5 animate-spin text-muted" aria-hidden />
                  <span role="status">Checking {file?.name}…</span>
                </>
              ) : (
                <>
                  <FileUp className="size-7 text-hue" strokeWidth={1.5} aria-hidden />
                  <span className="font-voice text-[21px] font-medium tracking-[-0.005em]">Choose a CSV file, or drop it here</span>
                  <span className="text-sm text-muted">
                    Needs {KINDS[kind].needs}. Nothing is added until you confirm.
                  </span>
                </>
              )}
              <input
                ref={input}
                type="file"
                accept=".csv,text/csv"
                className="sr-only"
                disabled={!!busy}
                onChange={(e) => {
                  const chosen = e.target.files?.[0];
                  if (chosen) void check(chosen);
                }}
              />
            </label>
          ) : (
            <Checked
              report={report}
              fileName={file?.name ?? ""}
              canAdd={!!s?.can_add}
              adding={busy === "adding"}
              outcome={KINDS[kind].outcome}
              onAdd={add}
              onCancel={start}
            />
          )}

          {error && (
            <p role="alert" className="mt-3 text-sm text-negative">
              {error}
            </p>
          )}

          {!report && (
            <div className="mt-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-2 text-sm">
              <p className="text-muted">{KINDS[kind].extra}</p>
              <button
                onClick={downloadSample}
                className="inline-flex items-center gap-1.5 font-medium hover:underline"
              >
                <Download className="size-3.5" aria-hidden /> Download a sample file
              </button>
            </div>
          )}

          {!report && (
            <div className="mt-4 overflow-x-auto border-t border-rule pt-3">
              <p className="mb-1 text-sm font-medium">What a good file looks like</p>
              <table className="w-full text-sm">
                <thead className="text-xs text-muted">
                  <tr>
                    {SAMPLE[kind].columns.map((c) => (
                      <th key={c} className="py-1.5 pr-4 text-left font-normal">
                        {c}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {SAMPLE[kind].rows.map((row) => (
                    <tr key={row.join()} className="border-t border-rule">
                      {row.map((v, i) => (
                        <td key={i} className="num py-1.5 pr-4">
                          {v}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <Panel title="Added so far">
          {status.isError ? (
            <BlockError onRetry={() => status.refetch()} />
          ) : !s ? (
            <Bar className="h-24 w-full" />
          ) : s.history.length === 0 ? (
            <p className="text-sm text-muted">No files added yet.</p>
          ) : (
            <ul>
              {s.history.map((h) => (
                <li key={`${h.created_at}-${h.filename}`} className="border-t border-rule py-2.5 first:border-t-0 first:pt-0">
                  <p className="truncate">{h.filename}</p>
                  <p className="num text-[13px] text-muted">
                    {KINDS[h.kind as Kind]?.label ?? h.kind}, {formatNumber(h.rows_added)} rows
                    {h.date_to ? `, to ${formatDate(h.date_to)}` : ""}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </>
  );
}

function Checked({
  report,
  fileName,
  canAdd,
  adding,
  outcome,
  onAdd,
  onCancel,
}: {
  report: ImportReport;
  fileName: string;
  canAdd: boolean;
  adding: boolean;
  outcome: string;
  onAdd: () => void;
  onCancel: () => void;
}) {
  const range =
    report.date_from && report.date_to
      ? report.date_from === report.date_to
        ? formatDate(report.date_from, { year: "numeric" })
        : `${formatDate(report.date_from)} to ${formatDate(report.date_to, { year: "numeric" })}`
      : "—";
  const facts = [
    ["Rows ready", formatNumber(report.rows_ok)],
    ["Rows skipped", formatNumber(report.rows_rejected)],
    ["Dates", range],
    ["Stores", formatNumber(report.stores)],
    ["Products", formatNumber(report.products)],
    ...(report.kind === "sales" ? [["Days replaced", formatNumber(report.rows_replacing)]] : []),
  ];
  return (
    <div>
      <h3 className="font-voice text-[21px] font-medium tracking-[-0.005em]">{fileName}</h3>
      <dl className="mt-2 grid gap-x-8 text-sm sm:grid-cols-2">
        {facts.map(([label, value]) => (
          <div key={label} className="flex justify-between gap-4 border-t border-rule py-2">
            <dt className="text-muted">{label}</dt>
            <dd className="num font-medium">{value}</dd>
          </div>
        ))}
      </dl>

      {report.issues.length > 0 && (
        <div className="mt-3">
          <h4 className="text-sm font-medium">
            {report.rows_rejected > report.issues.length
              ? `First ${report.issues.length} of ${formatNumber(report.rows_rejected)} rows skipped`
              : "Rows skipped"}
          </h4>
          <ul className="mt-1 text-sm">
            {report.issues.map((i) => (
              <li key={i.line} className="flex gap-3 py-1">
                <span className="num flex-none text-muted">Line {i.line}</span>
                <span>{i.problem}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <p className="mt-3 text-sm text-muted">
        {canAdd
          ? outcome
          : "Adding figures is switched off in this demo, so everyone sees the same store data."}
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        {canAdd && report.rows_ok > 0 && (
          <Button variant="primary" onClick={onAdd} disabled={adding}>
            {adding && <Loader2 className="size-4 animate-spin" aria-hidden />}
            {adding
              ? "Adding and updating forecasts…"
              : `Add ${formatNumber(report.rows_ok)} ${report.rows_ok === 1 ? "row" : "rows"}`}
          </Button>
        )}
        <Button onClick={onCancel} disabled={adding}>
          {canAdd ? "Choose another file" : "Check another file"}
        </Button>
      </div>
    </div>
  );
}
