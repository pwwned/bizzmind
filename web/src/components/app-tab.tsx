"use client";
/* The project's mini-app: an AI-designed working surface over the same data —
   entry forms, live KPIs and lists that replace the spreadsheet routine. */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, endpoints, p as apiPath, runJob } from "@/lib/api";
import { localeOf, useLang, useT } from "@/lib/i18n";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import Link from "next/link";
import { Blocks, Plus, RefreshCcw, Sparkles, Wallet } from "lucide-react";

interface Field { column: string; label: string; type?: string; required?: boolean; options_sql?: string }
interface View {
  type: "kpi" | "entry" | "table";
  title: string; hint?: string; table?: string; editable_table?: string; sql?: string;
  items?: { label: string; sql: string; unit?: string }[];
  fields?: Field[];
}
interface AppSpec { title?: string; subtitle?: string; views?: View[]; generated_at?: string }

function useSql(pid: string, sql?: string, key?: string) {
  return useQuery({
    queryKey: ["app-sql", pid, key ?? sql],
    queryFn: () => api<{ columns: string[]; rows: Record<string, unknown>[] }>(
      apiPath(pid, "/app/query"), { method: "POST", body: JSON.stringify({ sql }) }),
    enabled: !!sql,
    staleTime: 15_000,
  });
}

function KpiView({ pid, view }: { pid: string; view: View }) {
  const { lang } = useLang();
  return (
    <Card className="p-5">
      <h3 className="mb-3 text-[12px] font-bold uppercase tracking-wider text-muted-foreground">{view.title}</h3>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {(view.items ?? []).map((it) => <KpiItem key={it.label} pid={pid} item={it} loc={localeOf(lang)} />)}
      </div>
    </Card>
  );
}

function KpiItem({ pid, item, loc }: { pid: string; item: { label: string; sql: string; unit?: string }; loc: string }) {
  const q = useSql(pid, item.sql);
  const row = q.data?.rows?.[0];
  const raw = row ? Object.values(row)[0] : null;
  const val = typeof raw === "number" ? raw.toLocaleString(loc, { maximumFractionDigits: 2 }) : (raw ?? "—");
  return (
    <div className="rounded-xl border border-border bg-secondary/40 px-4 py-3">
      <div className="text-[11.5px] text-muted-foreground">{item.label}</div>
      <div className="mt-0.5 text-xl font-extrabold tabular-nums">
        {q.isLoading ? "…" : String(val)}
        {item.unit && <span className="ml-1 text-[11px] font-semibold text-muted-foreground">{item.unit}</span>}
      </div>
    </div>
  );
}

function EntryView({ pid, view }: { pid: string; view: View }) {
  const t = useT();
  const qc = useQueryClient();
  const [values, setValues] = useState<Record<string, string>>({});
  const save = useMutation({
    mutationFn: () => api<{ ok: boolean }>(apiPath(pid, "/app/row"),
      { method: "POST", body: JSON.stringify({ table: view.table, values }) }),
    onSuccess: () => {
      setValues({});
      toast.success(t("app_row_saved"));
      qc.invalidateQueries({ queryKey: ["app-sql", pid] });
      qc.invalidateQueries({ queryKey: ["state", pid] });
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const missing = (view.fields ?? []).some((f) => f.required && !values[f.column]?.trim());
  return (
    <Card className="p-5">
      <h3 className="text-[14px] font-bold">{view.title}</h3>
      {view.hint && <div className="mb-3 mt-0.5 text-[12px] text-muted-foreground">{view.hint}</div>}
      <form className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3"
        onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        {(view.fields ?? []).map((f) => (
          <FieldInput key={f.column} pid={pid} field={f}
            value={values[f.column] ?? ""} onChange={(v) => setValues({ ...values, [f.column]: v })} />
        ))}
        <div className="flex items-end sm:col-span-2 lg:col-span-3">
          <Button type="submit" disabled={missing || save.isPending}
            className="grad-olive font-bold text-primary-foreground hover:opacity-90">
            <Plus className="size-4" />{t("app_add_record")}
          </Button>
        </div>
      </form>
    </Card>
  );
}

function FieldInput({ pid, field, value, onChange }: { pid: string; field: Field; value: string; onChange: (v: string) => void }) {
  const opts = useSql(pid, field.type === "select" ? field.options_sql : undefined, `opt:${field.column}`);
  const cls = "h-9 rounded-lg border border-border bg-secondary/40 px-2.5 text-[13px] outline-none focus:border-olive";
  return (
    <label className="flex flex-col gap-1 text-[11px] font-semibold text-muted-foreground">
      {field.label}{field.required && <span className="text-olive"> *</span>}
      {field.type === "select" && opts.data ? (
        <select className={cls} value={value} onChange={(e) => onChange(e.target.value)}>
          <option value="">—</option>
          {opts.data.rows.map((r, i) => {
            const v = String(Object.values(r)[0] ?? "");
            return <option key={i} value={v}>{v}</option>;
          })}
        </select>
      ) : (
        <Input type={field.type === "number" ? "number" : field.type === "date" ? "date" : "text"}
          value={value} onChange={(e) => onChange(e.target.value)} className="h-9 text-[13px]" />
      )}
    </label>
  );
}

function TableView({ pid, view }: { pid: string; view: View }) {
  const { lang } = useLang();
  const loc = localeOf(lang);
  const q = useSql(pid, view.sql);
  return (
    <Card className="overflow-hidden p-0">
      <div className="border-b border-border px-5 py-3">
        <h3 className="text-[14px] font-bold">{view.title}</h3>
        {view.hint && <div className="mt-0.5 text-[12px] text-muted-foreground">{view.hint}</div>}
      </div>
      <div className="max-h-96 overflow-auto">
        <table className="w-full border-collapse text-[12.5px]">
          <thead className="sticky top-0 bg-card">
            <tr>{q.data?.columns.map((c) => (
              <th key={c} className="whitespace-nowrap px-4 py-2 text-left text-[10.5px] font-bold uppercase tracking-wider text-muted-foreground">
                {c.replace(/_/g, " ")}
              </th>))}
            </tr>
          </thead>
          <tbody>
            {q.data?.rows.map((r, i) => (
              <tr key={i} className="border-t border-border/60 hover:bg-secondary/40">
                {q.data!.columns.map((c) => {
                  const v = r[c];
                  return <td key={c} className={`px-4 py-1.5 ${typeof v === "number" ? "text-right tabular-nums" : ""}`}>
                    {typeof v === "number" ? v.toLocaleString(loc, { maximumFractionDigits: 2 }) : String(v ?? "")}
                  </td>;
                })}
              </tr>
            ))}
          </tbody>
        </table>
        {q.isLoading && <div className="p-5 text-sm text-muted-foreground">…</div>}
        {q.isError && <div className="p-5 text-sm text-destructive">{(q.error as Error).message}</div>}
      </div>
    </Card>
  );
}

export function AppTab({ pid, hasTables }: { pid: string; hasTables: boolean }) {
  const t = useT();
  const qc = useQueryClient();
  const [building, setBuilding] = useState(false);
  const [step, setStep] = useState("");
  const app = useQuery({
    queryKey: ["app", pid],
    queryFn: () => api<{ app: AppSpec }>(apiPath(pid, "/app")),
  });
  const quote = useQuery({
    queryKey: ["quote", pid, "app"],
    queryFn: () => endpoints.quote(pid, "analysis", "standard"),
    staleTime: 30_000,
  });

  async function build() {
    setBuilding(true);
    setStep("");
    try {
      await runJob(api(apiPath(pid, "/app/build"), { method: "POST" }), (ev) => setStep(ev.text));
      await qc.invalidateQueries({ queryKey: ["app", pid] });
      qc.invalidateQueries({ queryKey: ["account"] });
      toast.success(t("app_ready"));
    } catch (e) { toast.error((e as Error).message); }
    finally { setBuilding(false); setStep(""); }
  }

  const spec = app.data?.app;
  const views = spec?.views ?? [];

  if (building) {
    return (
      <div className="flex min-h-[55vh] flex-col items-center justify-center gap-4 text-center">
        <span className="size-9 animate-spin rounded-full border-[3px] border-border border-t-olive" />
        <div className="text-sm font-semibold">{t("app_building")}</div>
        {step && <div className="max-w-md text-[12px] text-muted-foreground">{step}</div>}
      </div>
    );
  }

  if (!views.length) {
    return (
      <div className="flex min-h-[55vh] flex-col items-center justify-center gap-4 text-center">
        <Blocks className="size-10 text-olive" />
        <h2 className="text-xl font-extrabold">{t("app_empty_title")}</h2>
        <p className="max-w-lg text-sm leading-relaxed text-muted-foreground">{t("app_empty_text")}</p>
        <Button disabled={!hasTables || quote.data?.affordable === false} onClick={build}
          className="grad-olive font-bold text-primary-foreground hover:opacity-90">
          <Sparkles className="size-4" />{t("app_build")}
          {quote.data && <span className="ml-1 text-[11px] opacity-80">{t("approx_cr", { n: quote.data.credits })}</span>}
        </Button>
        {quote.data?.affordable === false && (
          <div className="flex flex-col items-center gap-3">
            <div className="text-[12.5px] font-semibold text-destructive">
              {t("quote_short", { n: quote.data.credits, left: quote.data.remaining })}
            </div>
            <div className="flex flex-wrap justify-center gap-2">
              <Button size="sm" className="grad-olive font-bold text-primary-foreground hover:opacity-90"
                nativeButton={false} render={<Link href="/pricing" />}>
                <Wallet className="size-4" />{t("buy_credits")}
              </Button>
              <Button size="sm" variant="outline" nativeButton={false} render={<Link href="/pricing" />}>
                {t("see_pricing")}
              </Button>
            </div>
          </div>
        )}
        {!hasTables && <div className="text-[12px] text-muted-foreground">{t("app_needs_data")}</div>}
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-xl font-extrabold">{spec?.title}</h2>
          {spec?.subtitle && <div className="text-[13px] text-muted-foreground">{spec.subtitle}</div>}
        </div>
        <Button variant="outline" size="sm" onClick={build}>
          <RefreshCcw className="size-4" />{t("app_rebuild")}
        </Button>
      </div>
      {views.map((v, i) => (
        v.type === "kpi" ? <KpiView key={i} pid={pid} view={v} />
          : v.type === "entry" ? <EntryView key={i} pid={pid} view={v} />
            : <TableView key={i} pid={pid} view={v} />
      ))}
      {spec?.generated_at && <div className="text-[11px] text-muted-foreground">{t("app_generated", { at: spec.generated_at })}</div>}
    </div>
  );
}
