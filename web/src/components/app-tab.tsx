"use client";
/* The project's mini-app: an AI-designed working surface over the same data —
   entry forms, live KPIs and lists that replace the spreadsheet routine. */
import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, cancelJob, endpoints, JobCancelled, p as apiPath, runJob } from "@/lib/api";
import { localeOf, useLang, useT, type Key } from "@/lib/i18n";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Blocks, Check, ChevronDown, MessageCircle, Plus, RefreshCcw, Sparkles, Trash2, Wallet } from "lucide-react";
import { useBuyCredits } from "@/components/buy-credits";
import { useConfirm } from "@/components/confirm-dialog";
import { TabLoading } from "@/components/dashboard-empty";

interface Field { column: string; label: string; type?: string; required?: boolean; options_sql?: string }
interface View {
  type: "kpi" | "entry" | "table";
  title: string; hint?: string; table?: string; editable_table?: string; sql?: string;
  collapsible?: boolean; collapsed?: boolean; width?: "half" | "full";
  tables?: { table: string; label: string }[];
  items?: { label: string; sql: string; unit?: string }[];
  fields?: Field[];
}
interface AppSpec { title?: string; subtitle?: string; views?: View[]; generated_at?: string }
interface Proposal { id: string; title: string; pitch: string; does?: string[]; for_whom?: string; effort?: string }
interface AppPlan {
  reading?: string;
  proposals?: Proposal[];
  questions?: { question: string; options: string[] }[];
}

function useSql(pid: string, sql?: string, key?: string) {
  return useQuery({
    queryKey: ["app-sql", pid, key ?? sql],
    queryFn: () => api<{ columns: string[]; rows: Record<string, unknown>[] }>(
      apiPath(pid, "/app/query"), { method: "POST", body: JSON.stringify({ sql }) }),
    enabled: !!sql,
    staleTime: 15_000,
  });
}

function KpiView({ pid, view, inFold }: { pid: string; view: View; inFold?: boolean }) {
  const { lang } = useLang();
  return (
    <Card className={inFold ? "border-0 bg-transparent p-4 shadow-none" : "p-5"}>
      {!inFold && <h3 className="mb-3 text-[12px] font-bold uppercase tracking-wider text-muted-foreground">{view.title}</h3>}
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

function EntryView({ pid, view, inFold }: { pid: string; view: View; inFold?: boolean }) {
  const t = useT();
  const qc = useQueryClient();
  const options = view.tables ?? (view.table ? [{ table: view.table, label: view.title }] : []);
  const [target, setTarget] = useState(options[0]?.table ?? "");
  const [values, setValues] = useState<Record<string, string>>({});
  const save = useMutation({
    mutationFn: () => api<{ ok: boolean }>(apiPath(pid, "/app/row"),
      { method: "POST", body: JSON.stringify({ table: target || view.table, values }) }),
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
    <Card className={inFold ? "border-0 bg-transparent p-4 shadow-none" : "p-5"}>
      {!inFold && <h3 className="text-[14px] font-bold">{view.title}</h3>}
      {view.hint && <div className="mb-3 mt-0.5 text-[12px] text-muted-foreground">{view.hint}</div>}
      {options.length > 1 && (
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{t("app_site")}</span>
          <select value={target} onChange={(e) => setTarget(e.target.value)}
            className="h-9 min-w-52 rounded-lg border border-border bg-secondary/40 px-2.5 text-[13px] font-semibold outline-none focus:border-olive">
            {options.map((o) => <option key={o.table} value={o.table}>{o.label}</option>)}
          </select>
          <span className="text-[11.5px] text-muted-foreground">{t("app_site_hint", { n: options.length })}</span>
        </div>
      )}
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

function TableView({ pid, view, inFold }: { pid: string; view: View; inFold?: boolean }) {
  const { lang } = useLang();
  const loc = localeOf(lang);
  const q = useSql(pid, view.sql);
  return (
    <Card className={inFold ? "overflow-hidden border-0 bg-transparent p-0 shadow-none" : "overflow-hidden p-0"}>
      <div className={inFold ? "px-5 py-2" : "border-b border-border px-5 py-3"}>
        {!inFold && <h3 className="text-[14px] font-bold">{view.title}</h3>}
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

function Foldable({ view, children }: { view: View; children: React.ReactNode }) {
  const [open, setOpen] = useState(!view.collapsed);
  if (!view.collapsible) return <>{children}</>;
  return (
    <Card className="overflow-hidden p-0">
      <button type="button" onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-3 px-5 py-3.5 text-left transition-colors hover:bg-secondary/40">
        <span className="flex-1 text-[14.5px] font-bold">{view.title}</span>
        <ChevronDown className={`size-4 text-muted-foreground transition-transform ${open ? "" : "-rotate-90"}`} />
      </button>
      {open && <div className="border-t border-border p-1">{children}</div>}
    </Card>
  );
}

export function AppTab({ pid, hasTables, onAskChat }: {
  pid: string; hasTables: boolean; onAskChat?: (prompt: string) => void;
}) {
  const t = useT();
  const qc = useQueryClient();
  const buyCredits = useBuyCredits();
  const confirm = useConfirm();
  const [building, setBuilding] = useState(false);
  const [thinking, setThinking] = useState(false);
  const [step, setStep] = useState("");
  const runningJob = useRef<string | null>(null);
  const [plan, setPlan] = useState<AppPlan | null>(null);
  const [picked, setPicked] = useState<string>("");
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [extra, setExtra] = useState("");
  const app = useQuery({
    queryKey: ["app", pid],
    queryFn: () => api<{ app: AppSpec }>(apiPath(pid, "/app")),
  });
  const removeApp = useMutation({
    mutationFn: () => endpoints.deleteApp(pid),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["app", pid] }); setPlan(null); toast.success(t("app_deleted")); },
    onError: (e: Error) => toast.error(e.message),
  });
  const quote = useQuery({
    queryKey: ["quote", pid, "app"],
    queryFn: () => endpoints.quote(pid, "analysis", "standard"),
    staleTime: 30_000,
  });

  async function propose() {
    setThinking(true);
    setStep("");
    try {
      const r = await runJob<{ plan: AppPlan }>(api(apiPath(pid, "/app/propose"), { method: "POST" }), (ev) => setStep(ev.text), undefined, (id) => { runningJob.current = id; });
      setPlan(r.plan);
      setPicked(r.plan?.proposals?.[0]?.id ?? "");
      qc.invalidateQueries({ queryKey: ["account"] });
      qc.invalidateQueries({ queryKey: ["pres-credits", pid] });
    } catch (e) { if (!(e instanceof JobCancelled)) toast.error((e as Error).message); }
    finally { setThinking(false); setStep(""); runningJob.current = null; }
  }

  function composeBrief(): string {
    const chosen = plan?.proposals?.find((p) => p.id === picked);
    const parts: string[] = [];
    if (chosen) parts.push(`Chosen app: ${chosen.title} — ${chosen.pitch}\nIt should let people: ${(chosen.does ?? []).join("; ")}`);
    (plan?.questions ?? []).forEach((q, i) => { if (answers[i]) parts.push(`${q.question}\n→ ${answers[i]}`); });
    if (extra.trim()) parts.push(`The user also asks for: ${extra.trim()}`);
    return parts.join("\n\n");
  }

  async function build() {
    setBuilding(true);
    setStep("");
    try {
      await runJob(api(apiPath(pid, "/app/build"), { method: "POST", body: JSON.stringify({ brief: composeBrief() }) }), (ev) => setStep(ev.text), undefined, (id) => { runningJob.current = id; });
      await qc.invalidateQueries({ queryKey: ["app", pid] });
      qc.invalidateQueries({ queryKey: ["account"] });
      setPlan(null);
      toast.success(t("app_ready"));
    } catch (e) { if (!(e instanceof JobCancelled)) toast.error((e as Error).message); }
    finally { setBuilding(false); setStep(""); runningJob.current = null; }
  }

  const spec = app.data?.app;
  const views = spec?.views ?? [];

  // Until /app answers we do not know whether there is an app. Falling through
  // showed the "create your first app" screen to people who already had one.
  if (app.isLoading) return <TabLoading label={t("loading_app")} />;

  if (building || thinking) {
    return (
      <div className="flex min-h-[55vh] flex-col items-center justify-center gap-4 text-center">
        <span className="size-9 animate-spin rounded-full border-[3px] border-border border-t-olive" />
        <div className="text-sm font-semibold">{thinking ? t("app_thinking") : t("app_building")}</div>
        {step && <div className="max-w-md text-[12px] text-muted-foreground">{step}</div>}
        <Button variant="outline" size="sm"
          onClick={async () => { if (runningJob.current) await cancelJob(runningJob.current); }}>
          {t("stop")}
        </Button>
      </div>
    );
  }

  // proposal stage: what the AI suggests, what you want, what it must know
  if (plan && !views.length) {
    const chosen = plan.proposals?.find((p) => p.id === picked);
    return (
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-5">
        <div>
          <h2 className="text-xl font-extrabold">{t("app_plan_h")}</h2>
          {plan.reading && <p className="mt-1.5 text-[13.5px] leading-relaxed text-muted-foreground">{plan.reading}</p>}
        </div>
        <div className="grid gap-3">
          {(plan.proposals ?? []).map((p) => (
            <button key={p.id} type="button" onClick={() => setPicked(p.id)}
              className={`rounded-2xl border p-4 text-left transition-colors ${picked === p.id ? "border-olive bg-olive/10" : "border-border bg-card hover:border-olive/50"}`}>
              <div className="flex items-center gap-2">
                <span className={`inline-flex size-4 items-center justify-center rounded-full border ${picked === p.id ? "border-olive bg-olive" : "border-border"}`}>
                  {picked === p.id && <Check className="size-3 text-primary-foreground" />}
                </span>
                <b className="text-[15px]">{p.title}</b>
                {p.effort && <span className="rounded-full border border-border px-2 py-0.5 text-[10.5px] text-muted-foreground">{t(("effort_" + p.effort) as Key)}</span>}
              </div>
              <div className="mt-1.5 text-[13px] text-muted-foreground">{p.pitch}</div>
              {!!p.does?.length && (
                <ul className="mt-2 flex flex-col gap-1 text-[12.5px]">
                  {p.does.map((d) => <li key={d} className="flex gap-1.5"><span className="text-olive">·</span>{d}</li>)}
                </ul>
              )}
              {p.for_whom && <div className="mt-2 text-[11.5px] text-muted-foreground">{t("app_for_whom")}: {p.for_whom}</div>}
            </button>
          ))}
        </div>

        {(plan.questions ?? []).map((q, i) => (
          <div key={i} className="rounded-2xl border border-border bg-card p-4">
            <div className="text-[13.5px] font-semibold">{q.question}</div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {q.options.map((o) => (
                <button key={o} type="button" onClick={() => setAnswers({ ...answers, [i]: o })}
                  className={`rounded-full border px-3 py-1.5 text-[12.5px] transition-colors ${answers[i] === o ? "border-olive bg-olive/15 font-semibold" : "border-border text-muted-foreground hover:text-foreground"}`}>
                  {o}
                </button>
              ))}
            </div>
          </div>
        ))}

        <div className="rounded-2xl border border-border bg-card p-4">
          <div className="text-[13.5px] font-semibold">{t("app_your_input")}</div>
          <div className="mt-0.5 text-[11.5px] text-muted-foreground">{t("app_your_input_hint")}</div>
          <Input value={extra} onChange={(e) => setExtra(e.target.value)} placeholder={t("app_your_input_ph")} className="mt-2 text-[13px]" />
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Button disabled={!chosen || quote.data?.affordable === false} onClick={build}
            className="grad-olive font-bold text-primary-foreground hover:opacity-90">
            <Sparkles className="size-4" />{t("app_build")}
            {quote.data && <span className="ml-1 text-[11px] opacity-80">{t("approx_cr", { n: quote.data.credits })}</span>}
          </Button>
          <Button variant="ghost" onClick={() => setPlan(null)}>{t("cancel")}</Button>
          {quote.data?.affordable === false && (
            <Button size="sm" variant="outline" onClick={() => buyCredits(quote.data?.credits)}>
              <Wallet className="size-4" />{t("buy_credits")}
            </Button>
          )}
        </div>
      </div>
    );
  }

  if (!views.length) {
    return (
      <div className="flex min-h-[55vh] flex-col items-center justify-center gap-4 text-center">
        <Blocks className="size-10 text-olive" />
        <h2 className="text-xl font-extrabold">{t("app_empty_title")}</h2>
        <p className="max-w-lg text-sm leading-relaxed text-muted-foreground">{t("app_empty_text")}</p>
        <Button disabled={!hasTables} onClick={propose}
          className="grad-olive font-bold text-primary-foreground hover:opacity-90">
          <Sparkles className="size-4" />{t("app_propose")}
          <span className="ml-1 text-[11px] opacity-80">{t("approx_cr", { n: 40 })}</span>
        </Button>
        {quote.data?.affordable === false && (
          <div className="flex flex-col items-center gap-3">
            <div className="text-[12.5px] font-semibold text-destructive">
              {t("quote_short", { n: quote.data.credits, left: quote.data.remaining })}
            </div>
            <Button size="sm" className="grad-olive font-bold text-primary-foreground hover:opacity-90"
              onClick={() => buyCredits(quote.data?.credits)}>
              <Wallet className="size-4" />{t("buy_credits")}
            </Button>
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
        <div className="flex flex-wrap gap-2">
          {onAskChat && (
            <Button variant="outline" size="sm" onClick={() => onAskChat(t("app_edit_prompt"))}>
              <MessageCircle className="size-4" />{t("app_edit")}
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={propose}>
            <RefreshCcw className="size-4" />{t("app_rebuild")}
          </Button>
          <Button variant="ghost" size="sm" disabled={removeApp.isPending}
            className="text-destructive hover:bg-destructive/10 hover:text-destructive"
            onClick={async () => {
              if (await confirm({
                title: t("app_delete"), description: t("app_delete_confirm"),
                actionLabel: t("app_delete"), destructive: true,
              })) removeApp.mutate();
            }}>
            <Trash2 className="size-4" />{t("app_delete")}
          </Button>
        </div>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        {views.map((v, i) => (
          <div key={i} className={v.width === "half" ? "lg:col-span-1" : "lg:col-span-2"}>
            <Foldable view={v}>
              {v.type === "kpi" ? <KpiView pid={pid} view={v} inFold={!!v.collapsible} />
                : v.type === "entry" ? <EntryView pid={pid} view={v} inFold={!!v.collapsible} />
                  : <TableView pid={pid} view={v} inFold={!!v.collapsible} />}
            </Foldable>
          </div>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-olive/25 bg-olive/5 px-4 py-3 text-[12.5px]">
        <MessageCircle className="size-4 shrink-0 text-olive" />
        <span className="flex-1">{t("app_edit_hint")}</span>
        {onAskChat && (
          <Button size="sm" variant="outline" onClick={() => onAskChat(t("app_edit_prompt"))}>{t("app_edit")}</Button>
        )}
      </div>
      {spec?.generated_at && <div className="text-[11px] text-muted-foreground">{t("app_generated", { at: spec.generated_at })}</div>}
    </div>
  );
}
