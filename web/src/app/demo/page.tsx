"use client";
/* Public demo: the whole journey without an account and without AI spend —
   a real messy workbook is "processed" (recorded progress), the interview is
   replayed, and the dashboard at the end is genuinely live (SQL, no AI). */
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useLang, useT } from "@/lib/i18n";
import { Logo, Mark } from "@/components/logo";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/lib/theme";
import { useChromeHidden } from "@/lib/use-chrome-visibility";
import { ChartCard, useLabelMaps } from "@/components/chart-card";
import { FiltersBar, type Selections } from "@/components/filters-bar";
import type { Chart, Filter, I18nInfo } from "@/lib/api";
import { ArrowRight, FileSpreadsheet, Play, Sparkles } from "lucide-react";

interface DemoState { name: string; charts: Chart[]; filters: Filter[]; i18n?: I18nInfo; tables: { table: string; rows: number }[]; files: { filename: string; tables: string[] }[] }
interface Step { kind: string; text: string; at: number }
interface DemoScript { steps: Step[]; questions: { q: string; options: string[]; picked: string }[] }

type Phase = "intro" | "ingest" | "interview" | "dashboard";

export default function DemoPage() {
  const t = useT();
  const { lang, setLang } = useLang();
  const [phase, setPhase] = useState<Phase>("intro");
  const [shown, setShown] = useState<Step[]>([]);
  const [qIdx, setQIdx] = useState(0);
  const [selections, setSelections] = useState<Selections>({});
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const chromeHidden = useChromeHidden();

  const script = useQuery({ queryKey: ["demo-script"], queryFn: () => api<DemoScript>("/api/demo/script") });
  const state = useQuery({ queryKey: ["demo-state", lang], queryFn: () => api<DemoState>("/api/demo/state") });
  const hasSel = Object.values(selections).some((v) => (Array.isArray(v) ? v.length : !!v));
  const refresh = useQuery({
    queryKey: ["demo-refresh", selections],
    queryFn: () => api<{ charts: Chart[]; filters: Filter[] }>("/api/demo/refresh",
      { method: "POST", body: JSON.stringify({ selections }) }),
    enabled: phase === "dashboard" && hasSel,
    placeholderData: (p) => p,
  });
  const charts = hasSel && refresh.data ? refresh.data.charts : state.data?.charts ?? [];
  const i18n = state.data?.i18n;
  const { orig } = useLabelMaps(i18n);

  useEffect(() => () => timers.current.forEach(clearTimeout), []);

  function play() {
    const steps = script.data?.steps ?? [];
    setPhase("ingest");
    setShown([]);
    timers.current.forEach(clearTimeout);
    timers.current = steps.map((s, i) =>
      setTimeout(() => {
        setShown((prev) => [...prev, s]);
        if (i === steps.length - 1) setTimeout(() => setPhase("interview"), 700);
      }, s.at));
  }

  function answer() {
    const qs = script.data?.questions ?? [];
    if (qIdx + 1 < qs.length) setQIdx(qIdx + 1);
    else setTimeout(() => setPhase("dashboard"), 500);
  }

  function crossFilter(chart: Chart, label: string) {
    const f = state.data?.filters.find((x) => x.type === "multi" && x.column === chart.x_field);
    if (!f) return;
    const value = orig(label);
    const cur = (selections[f.id] as string[]) ?? [];
    setSelections({ ...selections, [f.id]: cur.length === 1 && cur[0] === value ? [] : [value] });
  }

  const qs = script.data?.questions ?? [];
  const q = qs[qIdx];
  const nTables = state.data?.tables.length ?? 12;

  return (
    <div className="flex min-h-screen flex-col">
      <header className={`sticky top-0 z-40 border-b border-border bg-background transition-transform duration-300 ${chromeHidden && phase === "dashboard" ? "-translate-y-full" : "translate-y-0"}`}>
        <div className={`mx-auto flex w-full items-center gap-4 px-6 py-3 ${phase === "dashboard" ? "max-w-[1800px]" : "max-w-6xl"}`}>
          <Link href="/"><Logo size={28} /></Link>
          <span className="rounded-full border border-olive/40 bg-olive/10 px-2.5 py-0.5 text-[11px] font-extrabold text-olive">{t("demo_badge")}</span>
          <span className="flex-1" />
          <div className="inline-flex overflow-hidden rounded-lg border border-border text-[11px] font-extrabold">
            {(["bg", "en"] as const).map((l) => (
              <button key={l} type="button" onClick={() => setLang(l)}
                className={`px-2.5 py-1.5 ${lang === l ? "grad-olive text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`}>{l.toUpperCase()}</button>
            ))}
          </div>
          <ThemeToggle />
          <Button size="sm" className="grad-olive font-bold text-primary-foreground" nativeButton={false} render={<Link href="/app" />}>{t("demo_try")}</Button>
        </div>
      </header>

      <main className={`mx-auto w-full flex-1 px-6 py-10 ${phase === "dashboard" ? "max-w-[1800px]" : "max-w-5xl"}`}>
        {phase === "intro" && (
          <div className="page-enter flex flex-col items-center gap-6 text-center">
            <h1 className="max-w-2xl text-3xl font-extrabold leading-tight sm:text-4xl">{t("demo_h1")}</h1>
            <p className="max-w-xl text-[15px] leading-relaxed text-muted-foreground">{t("demo_sub")}</p>
            <div className="w-full max-w-lg rounded-2xl border border-border bg-card p-5 text-left">
              <div className="flex items-center gap-3">
                <span className="inline-flex size-10 items-center justify-center rounded-xl border border-olive/30 bg-olive/10 text-olive"><FileSpreadsheet className="size-5" /></span>
                <span className="min-w-0 flex-1">
                  <b className="block truncate text-[14px]">РАПОРТ ЯНУАРИ 2024.xlsx</b>
                  <span className="text-[12px] text-muted-foreground">{t("demo_file_meta", { n: nTables })}</span>
                </span>
              </div>
              <div className="mt-3 flex flex-wrap gap-1.5 text-[11px]">
                {(t("demo_file_tags") as unknown as string).split("|").map((x) => (
                  <span key={x} className="rounded-full border border-border px-2 py-0.5 text-muted-foreground">{x}</span>
                ))}
              </div>
            </div>
            <Button size="lg" onClick={play} disabled={!script.data?.steps?.length}
              className="grad-olive font-bold text-primary-foreground hover:opacity-90">
              <Play className="size-4" />{t("demo_start")}
            </Button>
            <div className="text-[12px] text-muted-foreground">{t("demo_note")}</div>
          </div>
        )}

        {phase === "ingest" && (
          <div className="page-enter mx-auto max-w-2xl">
            <h2 className="text-xl font-extrabold">{t("demo_ingest_h")}</h2>
            <div className="mt-4 overflow-hidden rounded-2xl border border-border bg-card">
              <div className="border-b border-border bg-secondary/40 px-4 py-2 text-[11px] font-semibold text-muted-foreground">{t("s1_chrome_demo")}</div>
              <ul className="max-h-[420px] space-y-1 overflow-auto p-4 text-[12.5px]">
                {shown.map((s, i) => (
                  <li key={i} className={`flex gap-2 ${i === shown.length - 1 ? "text-foreground" : "text-muted-foreground"}`}>
                    <span className="shrink-0 text-olive">{s.kind === "table" ? "▤" : "·"}</span>
                    <span className="min-w-0 flex-1">{s.text}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}

        {phase === "interview" && q && (
          <div className="page-enter mx-auto max-w-2xl">
            <h2 className="text-xl font-extrabold">{t("demo_interview_h")}</h2>
            <p className="mt-1 text-[13.5px] text-muted-foreground">{t("demo_interview_p")}</p>
            <div className="mt-5 rounded-2xl border border-border bg-card p-5">
              <div className="flex gap-2.5">
                <span className="mt-0.5 inline-flex size-7 shrink-0 items-center justify-center rounded-full border border-olive/40 bg-olive/10"><Mark size={14} /></span>
                <div className="rounded-2xl rounded-tl-sm bg-secondary/70 px-3.5 py-2.5 text-[14px] leading-snug">{q.q}</div>
              </div>
              <div className="ml-10 mt-3 flex flex-wrap gap-2">
                {q.options.map((o) => (
                  <button key={o} type="button" onClick={answer}
                    className={`rounded-full border px-3 py-1.5 text-[13px] transition-colors ${o === q.picked ? "border-olive bg-olive/15 font-semibold" : "border-border text-muted-foreground hover:border-olive/50 hover:text-foreground"}`}>
                    {o}
                  </button>
                ))}
              </div>
              <div className="mt-4 text-right text-[11.5px] text-muted-foreground">{t("demo_q_of", { i: qIdx + 1, n: qs.length })}</div>
            </div>
          </div>
        )}

        {phase === "dashboard" && (
          <div className="page-enter">
            <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="text-xl font-extrabold">{state.data?.name}</h2>
                <div className="text-[12.5px] text-muted-foreground">{t("demo_dash_p")}</div>
              </div>
              <Button variant="outline" size="sm" nativeButton={false} render={<Link href="/app" />}>
                <Sparkles className="size-4" />{t("demo_cta_small")}
              </Button>
            </div>
            {state.data && (
              <div className={`sticky top-[57px] z-20 -mx-6 border-b border-border bg-background px-6 py-3 transition-transform duration-300 ${chromeHidden ? "-translate-y-[57px]" : "translate-y-0"}`}>
                <FiltersBar filters={(hasSel && refresh.data ? refresh.data.filters : state.data.filters)}
                  selections={selections} onChange={setSelections} i18n={i18n} />
              </div>
            )}
            <div className={`mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3 ${refresh.isFetching ? "opacity-70 transition-opacity" : ""}`}>
              {charts.map((c) => <ChartCard key={c.id} chart={c} i18n={i18n} onPick={crossFilter} wide={c.chart_type === "table"} />)}
            </div>
            <div className="mt-10 rounded-3xl border border-olive/40 bg-olive/5 p-8 text-center">
              <h3 className="text-2xl font-extrabold">{t("demo_cta_h")}</h3>
              <p className="mx-auto mt-2 max-w-lg text-[14px] text-muted-foreground">{t("demo_cta_p")}</p>
              <Button size="lg" className="grad-olive mt-5 font-bold text-primary-foreground hover:opacity-90"
                nativeButton={false} render={<Link href="/app" />}>{t("demo_cta_btn")}<ArrowRight className="size-4" /></Button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
