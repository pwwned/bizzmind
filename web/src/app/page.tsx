"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { endpoints } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { AppHeader } from "@/components/app-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Mark } from "@/components/logo";
import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

export default function ProjectsPage() {
  const t = useT();
  const qc = useQueryClient();
  const router = useRouter();
  const projects = useQuery({ queryKey: ["projects"], queryFn: endpoints.projects });
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");

  const create = useMutation({
    mutationFn: (n: string) => endpoints.createProject(n),
    onSuccess: (p) => { qc.invalidateQueries({ queryKey: ["projects"] }); router.push(`/p/${p.id}`); },
    onError: (e: Error) => toast.error(e.message),
  });
  const remove = useMutation({
    mutationFn: (pid: string) => endpoints.deleteProject(pid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
    onError: (e: Error) => toast.error(e.message),
  });

  const list = projects.data?.projects ?? [];

  return (
    <>
      <AppHeader />
      <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-8">
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
              <Input autoFocus placeholder={t("project_name_ph")} value={name} onChange={(e) => setName(e.target.value)} className="w-64" />
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
              className="group relative flex flex-col gap-3 rounded-2xl border border-border bg-card p-5 transition-all hover:-translate-y-0.5 hover:border-olive/50 hover:shadow-[0_10px_40px_rgba(181,211,61,0.12)]">
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
                onClick={(e) => {
                  e.preventDefault(); e.stopPropagation();
                  if (confirm(t("confirm_delete_project", { name: p.name }))) remove.mutate(p.id);
                }}
              >
                <Trash2 className="size-4" />
              </button>
            </Link>
          ))}
        </div>
      </main>
    </>
  );
}
