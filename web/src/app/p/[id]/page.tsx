"use client";
import { use, useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { cacheGet, cacheSet, endpoints, useCachedPlaceholder, type Chart, type ProjectState } from "@/lib/api";
import { useLang } from "@/lib/i18n";
import { useT } from "@/lib/i18n";
import { AppHeader } from "@/components/app-header";
import { ChartCard, useLabelMaps } from "@/components/chart-card";
import { FiltersBar, type Selections } from "@/components/filters-bar";
import { DashboardEmpty, DashboardLoading } from "@/components/dashboard-empty";
import { FilesTab } from "@/components/files-tab";
import { DataTab } from "@/components/data-tab";
import { AppTab } from "@/components/app-tab";
import { ChatPanel } from "@/components/chat-panel";
import Link from "next/link";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useChromeHidden } from "@/lib/use-chrome-visibility";
import { Button } from "@/components/ui/button";
import { PresentationDialog } from "@/components/presentation-dialog";

type Tab = "dash" | "app" | "files" | "data";

export default function ProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id: pid } = use(params);
  const t = useT();
  const [tab, setTab] = useState<Tab>("dash");
  const [selections, setSelections] = useState<Selections>({});
  const [chatOpen, setChatOpen] = useState(false);
  const [pendingReview, setPendingReview] = useState<{ tables: string[] } | null>(null);
  const uploadRef = useRef<(() => void) | null>(null);
  const chromeHidden = useChromeHidden();

  const { lang } = useLang();
  const hydrated = useCachedPlaceholder();
  const state = useQuery({
    queryKey: ["state", pid],
    queryFn: async () => { const d = await endpoints.state(pid); cacheSet(`state:${pid}:${lang}`, d); return d; },
    placeholderData: () => (hydrated ? cacheGet<ProjectState>(`state:${pid}:${lang}`) : undefined),
  });
  const hasSel = Object.values(selections).some((v) => (Array.isArray(v) ? v.length : !!v));
  const refresh = useQuery({
    queryKey: ["refresh", pid, selections],
    queryFn: () => endpoints.refresh(pid, selections),
    enabled: !!state.data && hasSel,
    placeholderData: (prev) => prev,
  });

  useEffect(() => { setSelections({}); setTab("dash"); }, [pid]);

  const charts: Chart[] = hasSel && refresh.data ? refresh.data.charts : state.data?.charts ?? [];
  const i18n = useMemo(() => {
    if (!state.data) return undefined;
    const extra = refresh.data?.i18n;
    return extra ? { ...state.data.i18n, value_labels: { ...state.data.i18n.value_labels, ...extra.value_labels } } : state.data.i18n;
  }, [state.data, refresh.data]);
  const { orig } = useLabelMaps(i18n);

  function crossFilter(chart: Chart, label: string) {
    if (!state.data) return;
    const value = orig(label);
    const f = state.data.filters.find((x) => x.type === "multi" && x.column === chart.x_field)
      ?? state.data.filters.find((x) => x.type === "multi" && x.resolved_options.includes(value));
    if (!f) return;
    const cur = (selections[f.id] as string[]) ?? [];
    setSelections({ ...selections, [f.id]: cur.length === 1 && cur[0] === value ? [] : [value] });
  }

  return (
    <>
      <AppHeader crumb={state.data?.name ?? ""} back autoHide />
      <div className="flex min-h-0 flex-1 flex-col">
        <div className={`sticky top-[57px] z-30 flex items-center gap-4 border-b border-border bg-background px-6 transition-transform duration-300 ${chromeHidden ? "-translate-y-[101px]" : "translate-y-0"}`}>
          <Tabs value={tab} onValueChange={(v) => setTab(v as Tab)}>
            <TabsList className="h-11 bg-transparent p-0">
              {(["dash", "app", "files", "data"] as Tab[]).map((k) => (
                <TabsTrigger key={k} value={k}
                  className="rounded-none border-b-2 border-transparent px-4 text-[13.5px] font-semibold text-muted-foreground data-[state=active]:border-olive data-[state=active]:bg-transparent data-[state=active]:text-foreground data-[state=active]:shadow-none">
                  {t(k === "dash" ? "tab_dash" : k === "app" ? "tab_app" : k === "files" ? "tab_files" : "tab_data")}
                  {k === "app" && <span className="ml-1.5 rounded bg-olive/20 px-1 text-[9px] font-extrabold text-olive">BETA</span>}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        </div>

        <main key={pid} className="page-enter flex min-h-0 flex-1 flex-col px-6 py-5">
          {!state.data ? (
            state.isError ? (
              <div className="flex min-h-[55vh] flex-col items-center justify-center gap-4 text-center">
                <div className="text-lg font-bold">{t("project_missing")}</div>
                <Button nativeButton={false} render={<Link href="/app" />} variant="outline">{t("all_projects")}</Button>
              </div>
            ) : (
              <DashboardLoading />
            )
          ) : tab === "dash" ? (
            charts.length === 0 && !hasSel ? (
              <DashboardEmpty
                hasTables={state.data.tables.length > 0}
                onStart={() => {
                  if (state.data && state.data.tables.length > 0) {
                    setPendingReview({ tables: state.data.tables.map((x) => x.table) });
                    setChatOpen(true);
                  } else {
                    setTab("files");
                    setTimeout(() => uploadRef.current?.(), 250);
                  }
                }}
              />
            ) : (
              <>
                <div className={`sticky top-[101px] z-20 -mx-6 mb-4 flex flex-wrap items-start justify-between gap-3 border-b border-border bg-background px-6 py-3 transition-transform duration-300 ${chromeHidden ? "-translate-y-[101px] opacity-0" : "translate-y-0 opacity-100"}`}>
                  <FiltersBar filters={(hasSel && refresh.data ? refresh.data.filters : state.data.filters)} selections={selections} onChange={setSelections} i18n={i18n} />
                  <PresentationDialog pid={pid} name={state.data.name} charts={state.data.charts} i18n={i18n} brandPrimary={state.data.brand_theme?.primary ?? ""} />
                </div>
                <div className={`grid gap-4 md:grid-cols-2 xl:grid-cols-3 ${refresh.isFetching ? "opacity-70 transition-opacity" : ""}`}>
                  {charts.map((c) => <ChartCard key={c.id} chart={c} i18n={i18n} onPick={crossFilter} wide={c.chart_type === "table"} />)}
                </div>
              </>
            )
          ) : tab === "app" ? (
            <AppTab pid={pid} hasTables={state.data.tables.length > 0} />
          ) : tab === "files" ? (
            <FilesTab pid={pid} state={state.data as ProjectState} uploadRef={uploadRef}
              onUploaded={(tables) => { setPendingReview({ tables }); }} />
          ) : (
            <DataTab pid={pid} state={state.data as ProjectState} />
          )}
        </main>
      </div>
      {state.data && (
        <ChatPanel pid={pid} initial={state.data.chat} open={chatOpen} onOpenChange={setChatOpen} pending={pendingReview} />
      )}
    </>
  );
}
