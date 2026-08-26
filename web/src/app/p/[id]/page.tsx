"use client";
import { use, useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { cacheGet, cacheSet, endpoints, type Chart, type ProjectState } from "@/lib/api";
import { useLang } from "@/lib/i18n";
import { useT } from "@/lib/i18n";
import { AppHeader } from "@/components/app-header";
import { ChartCard, useLabelMaps } from "@/components/chart-card";
import { FiltersBar, type Selections } from "@/components/filters-bar";
import { DashboardEmpty, DashboardLoading } from "@/components/dashboard-empty";
import { FilesTab } from "@/components/files-tab";
import { DataTab } from "@/components/data-tab";
import { ChatPanel } from "@/components/chat-panel";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Presentation } from "lucide-react";

type Tab = "dash" | "files" | "data";

export default function ProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id: pid } = use(params);
  const t = useT();
  const [tab, setTab] = useState<Tab>("dash");
  const [selections, setSelections] = useState<Selections>({});
  const [chatOpen, setChatOpen] = useState(false);
  const [pendingReview, setPendingReview] = useState<{ tables: string[] } | null>(null);
  const uploadRef = useRef<(() => void) | null>(null);

  const { lang } = useLang();
  const state = useQuery({
    queryKey: ["state", pid],
    queryFn: async () => { const d = await endpoints.state(pid); cacheSet(`state:${pid}:${lang}`, d); return d; },
    placeholderData: () => cacheGet<ProjectState>(`state:${pid}:${lang}`),
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
      <AppHeader crumb={state.data?.name ?? ""} back />
      <div className="flex min-h-0 flex-1 flex-col">
        <div className="flex items-center gap-4 border-b border-border px-6">
          <Tabs value={tab} onValueChange={(v) => setTab(v as Tab)}>
            <TabsList className="h-11 bg-transparent p-0">
              {(["dash", "files", "data"] as Tab[]).map((k) => (
                <TabsTrigger key={k} value={k}
                  className="rounded-none border-b-2 border-transparent px-4 text-[13.5px] font-semibold text-muted-foreground data-[state=active]:border-olive data-[state=active]:bg-transparent data-[state=active]:text-foreground data-[state=active]:shadow-none">
                  {t(k === "dash" ? "tab_dash" : k === "files" ? "tab_files" : "tab_data")}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        </div>

        <main key={pid} className={`page-enter flex min-h-0 flex-1 flex-col px-6 py-5 transition-[padding] ${chatOpen ? "lg:pr-[440px]" : ""}`}>
          {!state.data ? (
            <DashboardLoading />
          ) : tab === "dash" ? (
            charts.length === 0 && !hasSel ? (
              <DashboardEmpty onStart={() => { setTab("files"); setTimeout(() => uploadRef.current?.(), 250); }} />
            ) : (
              <>
                <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
                  <FiltersBar filters={(hasSel && refresh.data ? refresh.data.filters : state.data.filters)} selections={selections} onChange={setSelections} i18n={i18n} />
                  <Button variant="outline" size="sm" className="ml-auto"><Presentation className="size-4" />{t("presentation")}</Button>
                </div>
                <div className={`grid gap-4 md:grid-cols-2 xl:grid-cols-3 ${refresh.isFetching ? "opacity-70 transition-opacity" : ""}`}>
                  {charts.map((c) => <ChartCard key={c.id} chart={c} i18n={i18n} onPick={crossFilter} wide={c.chart_type === "table"} />)}
                </div>
              </>
            )
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
