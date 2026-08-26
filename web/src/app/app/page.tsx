"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { cacheGet, cacheSet, endpoints, useCachedPlaceholder, type ProjectCard, type ProjectState } from "@/lib/api";
import { useT, useLang } from "@/lib/i18n";
import { AppHeader } from "@/components/app-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Mark } from "@/components/logo";
import { Plus, Trash2 } from "lucide-react";

import { toast } from "sonner";
import { useConfirm } from "@/components/confirm-dialog";

export default function ProjectsPage() {
  const t = useT();
  const qc = useQueryClient();
  const router = useRouter();
  const confirm = useConfirm();
  const hydrated = useCachedPlaceholder();
  const projects = useQuery({
    queryKey: ["projects"],
    queryFn: async () => { const d = await endpoints.projects(); cacheSet("projects", d); return d; },
    placeholderData: () => (hydrated ? cacheGet<{ projects: ProjectCard[] }>("projects") : undefined),
  });
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [opening, setOpening] = useState<string | null>(null);   // pid being opened, or "new"
  const { lang } = useLang();

  const create = useMutation({
    mutationFn: (n: string) => endpoints.createProject(n),
    onSuccess: (proj) => {
      // Seed an empty state so the project opens instantly on the guided empty screen.
      const empty: ProjectState = {
        name: proj.name, tables: [], charts: [], notes: [], filters: [], chat: [],
        brand: [], brand_theme: { primary: "", accent: "" }, brand_logo: null,
        brand_colors: [], brand_fonts: [], files: [],
        i18n: { content_lang: lang, ui_lang: lang, needs_translation: false, field_labels: {}, value_labels: {} },
      };
      qc.setQueryData(["state", proj.id], empty);
      cacheSet(`state:${proj.id}:${lang}`, empty);
      qc.invalidateQueries({ queryKey: ["projects"], refetchType: "none" });   // no card popping in mid-transition
      setOpening("new");
      router.push(`/p/${proj.id}`);
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const remove = useMutation({
    mutationFn: (pid: string) => endpoints.deleteProject(pid),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["projects"] }); toast.success(t("project_deleted")); },
    onError: (e: Error) => toast.error(e.message),
  });

  const list = projects.data?.projects ?? [];

  return (
    <>
      <AppHeader />
      <main className="page-enter mx-auto w-full max-w-6xl flex-1 px-6 py-8">
        <div className="mb-6 flex items-end justify-between gap-4">
          <div>
            <h1 className="text-2xl font-extrabold">{t("projects")}</h1>
          </div>
          {!creating ? (
            <Button onClick={() => setCreating(true)} className="grad-olive font-bold text-primary-foreground hover:opacity-90">
              <Plus className="size-4" />{t("new_project")}
            </Button>
          ) : (
            <form className="flex items-center gap-2" onSubmit={(e) => { e.preventDefault(); if (name.trim()) create.mutate(name.trim()); }}>
              <Input autoFocus disabled={create.isPending} placeholder={t("project_name_ph")} value={name} onChange={(e) => setName(e.target.value)} className="w-64" />
              <Button type="submit" disabled={create.isPending || !name.trim()} className="grad-olive font-bold text-primary-foreground">{t("create")}</Button>
              <Button type="button" variant="ghost" onClick={() => { setCreating(false); setName(""); }}>{t("cancel")}</Button>
            </form>
          )}
        </div>

        {projects.isLoading && (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[0, 1, 2].map((i) => <Skeleton key={i} className="h-36 rounded-2xl" />)}
          </div>
        )}

        {projects.data && list.length === 0 && (
          <div className="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-border p-16 text-center">
            <Mark size={48} />
            <h2 className="text-lg font-bold">{t("no_projects_title")}</h2>
            <p className="max-w-md text-sm text-muted-foreground">{t("no_projects_text")}</p>
          </div>
        )}

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {list.map((p) => (
            <Link key={p.id} href={`/p/${p.id}`}
              onClick={(e) => { if (!e.metaKey && !e.ctrlKey && !e.shiftKey && e.button === 0) setOpening(p.id); }}
              className={`group relative flex flex-col gap-3 rounded-2xl border border-border bg-card p-5 transition-all hover:-translate-y-0.5 hover:border-olive/50 hover:shadow-[0_10px_40px_rgba(181,211,61,0.12)] ${opening && opening !== p.id ? "opacity-50" : ""}`}>
              {opening === p.id && (
                <span className="absolute inset-0 z-10 flex items-center justify-center rounded-2xl bg-card/70 backdrop-blur-[2px]">
                  <span className="size-6 animate-spin rounded-full border-2 border-border border-t-olive" />
                </span>
              )}
              <h3 className="truncate text-base font-bold">{p.name}</h3>
              <div className="text-xs text-muted-foreground">{t("created")} {p.created || "—"}</div>
              <div className="mt-auto flex gap-4 text-xs text-muted-foreground">
                <span><b className="text-olive">{p.tables}</b> {t("tables")}</span>
                <span><b className="text-olive">{p.charts}</b> {t("charts")}</span>
                <span><b className="text-olive">{p.notes}</b> {t("knowledge")}</span>
              </div>
              <button
                type="button"
                title={t("delete_project")}
                className="absolute right-3 top-3 rounded-md p-1.5 text-muted-foreground opacity-0 transition-opacity hover:bg-destructive/15 hover:text-destructive group-hover:opacity-100"
                onClick={async (e) => {
                  e.preventDefault(); e.stopPropagation();
                  if (await confirm({ title: t("delete_project"), description: t("confirm_delete_project", { name: p.name }), actionLabel: t("delete"), destructive: true })) remove.mutate(p.id);
                }}
              >
                <Trash2 className="size-4" />
              </button>
            </Link>
          ))}
        </div>
      </main>
      {(create.isPending || opening === "new") && (
        <div className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-4 bg-background/70 backdrop-blur-sm">
          <span className="size-10 animate-spin rounded-full border-[3px] border-border border-t-olive" />
          <div className="text-sm font-semibold">{t("creating_project")}</div>
        </div>
      )}
    </>
  );
}
