"use client";

import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { BarChart3, FileUp, Package, Sparkles } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { type Alerts, api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { ScopeProvider, useScope } from "@/lib/scope";
import { ThemeCycle, ThemeSwitch } from "@/lib/theme";
import { ShelfMark } from "./mark";
import { Select } from "./select";
import { useServerReady, WakeBanner } from "./wake-banner";

const NAV = [
  { href: "/dashboard", label: "Overview", icon: BarChart3 },
  { href: "/forecast", label: "Stock", icon: Package },
  { href: "/analyst", label: "Analyst", icon: Sparkles },
  { href: "/data", label: "Data", icon: FileUp },
] as const;

function ScopeSelect({ className, align }: { className?: string; align?: "left" | "right" }) {
  const { storeId, setStoreId, stores } = useScope();
  return (
    <Select
      label="Store"
      value={storeId}
      onChange={setStoreId}
      align={align}
      className={className}
      options={[
        { value: "", label: "All 8 stores", note: "The whole chain" },
        ...stores.map((s) => ({
          value: String(s.id),
          label: s.name,
          note: `${s.city} · ${s.format}`,
        })),
      ]}
    />
  );
}

/** Labelled sidebar on the page ground: the product, its scope, three destinations. */
function Sidebar() {
  const pathname = usePathname();
  const { storeId } = useScope();
  const alerts = useQuery({
    queryKey: ["alerts-count", storeId],
    queryFn: () =>
      api<Alerts>("/api/forecast/alerts", { status: "stockout_risk", store_id: storeId, limit: 1 }),
  });
  const atRisk = alerts.data?.counts.stockout_risk;

  return (
    <aside className="sticky top-0 hidden h-screen flex-col px-3 py-4 md:flex">
      <Link href="/" className="flex items-center gap-2 px-2 font-voice text-[19px] font-semibold tracking-[-0.01em]">
        <ShelfMark size={24} className="text-hue" />
        ShelfIQ
      </Link>
      <div className="mt-5 px-1">
        <p className="mb-1 px-1 text-xs text-muted">Haat Retail</p>
        <ScopeSelect className="w-full" />
      </div>
      <nav aria-label="Main" className="mt-5 grid gap-0.5">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={clsx(
                "flex h-9 items-center gap-2.5 rounded-md px-2.5 transition-colors",
                active ? "bg-active font-medium text-active-ink" : "text-muted hover:bg-raised hover:text-ink",
              )}
            >
              <Icon className={clsx("size-4", active && "text-hue")} strokeWidth={1.7} aria-hidden />
              {label}
              {href === "/forecast" && atRisk ? (
                <span className="num ml-auto rounded bg-pill-negative-bg px-1.5 text-xs font-medium text-pill-negative-ink">
                  {atRisk}
                  <span className="sr-only"> shelves running out</span>
                </span>
              ) : null}
            </Link>
          );
        })}
      </nav>
      <div className="mt-auto grid gap-3 px-2 text-xs text-muted">
        <div>
          <p className="mb-1">Appearance</p>
          <ThemeSwitch className="w-full" />
        </div>
        <p>
          {alerts.data ? `Figures to ${formatDate(alerts.data.as_of, { year: "numeric" })}` : ""}
        </p>
      </div>
    </aside>
  );
}

function PhoneBars() {
  const pathname = usePathname();
  return (
    <>
      <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-2 md:hidden">
        <Link href="/" className="flex items-center gap-1.5 font-voice font-semibold">
          <ShelfMark size={20} className="text-hue" /> ShelfIQ
        </Link>
        <div className="flex min-w-0 items-center gap-1">
          <ThemeCycle className="text-muted" />
          <ScopeSelect className="w-40" align="right" />
        </div>
      </div>
      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-4 border-t border-line bg-surface md:hidden"
      >
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={clsx(
                "flex h-14 flex-col items-center justify-center gap-0.5 text-xs",
                active ? "font-medium text-hue" : "text-muted",
              )}
            >
              <Icon className="size-[18px]" strokeWidth={1.7} aria-hidden />
              {label}
            </Link>
          );
        })}
      </nav>
    </>
  );
}

// Pages render their own loading bars at once; the API client signs in to the demo on
// first use (see ensureSession), so deep links work without a login step.
export function AppShell({ children }: { children: ReactNode }) {
  const server = useServerReady();
  return (
    <ScopeProvider>
      <div className="min-h-screen md:grid md:grid-cols-[224px_minmax(0,1fr)] md:bg-frame">
        <Sidebar />
        <div className="min-w-0 md:my-2 md:mr-2 md:min-h-[calc(100vh-16px)] md:rounded-2xl md:border md:border-line md:bg-ground">
          <PhoneBars />
          <main className="mx-auto w-full max-w-[1320px] px-4 pt-5 pb-24 sm:px-8 md:pt-7 md:pb-12">
            {server.slow && (
              <div className="mb-4">
                <WakeBanner show />
              </div>
            )}
            {children}
          </main>
        </div>
      </div>
    </ScopeProvider>
  );
}

/** Title row: the screen's noun as h1, its one finding, and the main action on the right. */
export function TitleRow({
  title,
  finding,
  actions,
}: {
  title: string;
  finding?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="mb-5 flex flex-wrap items-start justify-between gap-x-8 gap-y-3">
      <div className="min-w-0 flex-1 basis-96">
        <h1 className="font-voice text-[28px] leading-9 font-medium tracking-[-0.015em]">{title}</h1>
        {finding && <p className="mt-1 max-w-3xl text-[15px] leading-6">{finding}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}
