"use client";
import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useConfirm } from "@/components/confirm-dialog";
import { api, ApiError, endpoints, p, runJob, type ProjectState } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ChevronDown, FileSpreadsheet, Palette, Brain, Trash2, Plus, AlertTriangle } from "lucide-react";

function Section({ icon, title, hint, count, children, defaultOpen = true }: {
  icon: React.ReactNode; title: string; hint?: string; count: number; children: React.ReactNode; defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Card className="p-5">
      <button type="button" onClick={() => setOpen(!open)} className="flex w-full items-center gap-3 text-left">
        <span className="inline-flex size-9 items-center justify-center rounded-xl border border-olive/30 bg-olive/10 text-olive">{icon}</span>
        <span className="flex-1">
          <h3 className="text-[14.5px] font-bold">{title}</h3>
          {hint && <div className="text-xs text-muted-foreground">{hint}</div>}
        </span>
        <span className="rounded-full border border-olive/30 bg-olive/10 px-2.5 py-0.5 text-[11px] font-extrabold text-olive">{count}</span>
        <ChevronDown className={`size-4 text-muted-foreground transition-transform ${open ? "" : "-rotate-90"}`} />
      </button>
      {open && <div className="mt-4 flex flex-col gap-3">{children}</div>}
    </Card>
  );
}

export function FilesTab({ pid, state, onUploaded, uploadRef }: {
  pid: string; state: ProjectState; onUploaded: (tables: string[]) => void;
  uploadRef?: React.MutableRefObject<(() => void) | null>;
}) {
  const t = useT();
  const qc = useQueryClient();
  const confirm = useConfirm();
  const input = useRef<HTMLInputElement>(null);
  const brandInput = useRef<HTMLInputElement>(null);
  const [note, setNote] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState("");
  if (uploadRef) uploadRef.current = () => input.current?.click();

  async function upload(files: FileList | null) {
    if (!files?.length) return;
    setUploading(true);
    try {
      const list = Array.from(files);
      let r: { loaded: { table: string; rows: number }[] };
      try {
        // 1) signed URLs → 2) browser PUTs straight to Supabase Storage (no API body limit) → 3) API ingests
        console.info("[upload] sign:", list.map((f) => `${f.name} (${(f.size / 1048576).toFixed(1)}MB)`));
        const sign = await api<{ files: { filename: string; url: string }[] }>(p(pid, "/upload/sign"),
          { method: "POST", body: JSON.stringify({ filenames: list.map((f) => f.name) }) });
        console.info("[upload] signed", sign.files.length, "url(s), starting PUTs");
        await Promise.all(sign.files.map(async (s) => {
          const f = list.find((x) => x.name === s.filename)!;
          const res = await fetch(s.url, { method: "PUT", body: f, headers: { "x-upsert": "true", "Content-Type": f.type || "application/octet-stream" } });
          if (!res.ok) {
            const body = (await res.text().catch(() => "")).slice(0, 200);
            console.error("[upload] PUT failed:", s.filename, res.status, body);
            throw new Error(`${s.filename}: storage HTTP ${res.status} ${body}`);
          }
          console.info("[upload] PUT ok:", s.filename);
        }));
        console.info("[upload] ingest starting (background job)");
        r = await runJob<{ loaded: { table: string; rows: number }[] }>(
          api(p(pid, "/upload/ingest"), { method: "POST", body: JSON.stringify({ filenames: sign.files.map((s) => s.filename) }) }),
          (ev) => setUploadMsg(ev.text),
        );
        console.info("[upload] ingest done:", r.loaded.length, "table(s)");
      } catch (e) {
        // a dropped/timed-out ingest request does not mean a failed ingest:
        // the server may have finished — check the project state before failing
        console.warn("[upload] request failed, verifying server state:", (e as Error).message);
        await new Promise((res) => setTimeout(res, 3000));
        const st = await api<ProjectState>(p(pid, "/state")).catch(() => null);
        const landed = st?.files?.find((x) => list.some((f) => f.name === x.filename));
        if (landed) {
          console.info("[upload] server finished despite the dropped request — continuing");
          r = { loaded: landed.tables.map((t) => ({ table: t, rows: 0 })) };
        } else if (e instanceof ApiError && e.status === 503) {
          const fd = new FormData();               // storage not configured → direct upload
          for (const f of list) fd.append("files", f);
          r = await api(p(pid, "/upload"), { method: "POST", body: fd });
        } else {
          throw e;
        }
      }
      await qc.invalidateQueries({ queryKey: ["state", pid] });
      toast.success(t("upload_done", { n: r.loaded.length }));
      onUploaded(r.loaded.map((l) => l.table));
    } catch (e) { toast.error((e as Error).message); }
    finally { setUploading(false); setUploadMsg(""); if (input.current) input.current.value = ""; }
  }
  async function uploadBrand(files: FileList | null) {
    if (!files?.length) return;
    try {
      const fd = new FormData();
      for (const f of Array.from(files)) fd.append("files", f);
      await api(p(pid, "/brand"), { method: "POST", body: fd });
      qc.invalidateQueries({ queryKey: ["state", pid] });
    } catch (e) { toast.error((e as Error).message); }
  }
  const delFile = useMutation({ mutationFn: (f: string) => endpoints.deleteFile(pid, f), onSuccess: () => { qc.invalidateQueries({ queryKey: ["state", pid] }); toast.success(t("file_deleted")); }, onError: (e: Error) => toast.error(e.message) });
  const delBrand = useMutation({ mutationFn: (f: string) => api(p(pid, `/brand/${encodeURIComponent(f)}`), { method: "DELETE" }), onSuccess: () => qc.invalidateQueries({ queryKey: ["state", pid] }) });
  const addNote = useMutation({ mutationFn: (n: string) => endpoints.addNote(pid, n), onSuccess: () => { setNote(""); qc.invalidateQueries({ queryKey: ["state", pid] }); } });
  const delNote = useMutation({ mutationFn: (i: number) => api(p(pid, `/notes/${i}`), { method: "DELETE" }), onSuccess: () => qc.invalidateQueries({ queryKey: ["state", pid] }) });
  const clearProject = useMutation({
    mutationFn: () => endpoints.reset(pid),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["state", pid] });
      qc.invalidateQueries({ queryKey: ["app", pid] });
      toast.success(t("project_cleared"));
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-4">
      <Section icon={<FileSpreadsheet className="size-4" />} title={t("files_title")} hint={t("files_hint")} count={state.files.length}>
        <div
          onClick={() => input.current?.click()}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => { e.preventDefault(); upload(e.dataTransfer.files); }}
          className="cursor-pointer rounded-xl border-2 border-dashed border-border p-6 text-center text-sm text-muted-foreground transition-colors hover:border-olive hover:bg-olive/5"
        >
          {uploading ? (uploadMsg || t("uploading")) : t("drop_files")}
          <input ref={input} type="file" multiple accept=".xlsx,.xls,.csv" hidden onChange={(e) => upload(e.target.files)} />
        </div>
        <ul className="flex max-h-80 flex-col gap-2 overflow-auto">
          {state.files.map((f) => (
            <li key={f.filename} className="group flex items-center gap-3 rounded-lg border border-border bg-secondary/40 px-3 py-2 text-sm">
              <FileSpreadsheet className="size-4 text-olive" />
              <span className="flex-1 truncate" title={f.filename}>{f.filename}</span>
              <span className="text-xs text-muted-foreground">{f.tables.length} {t("tables")}</span>
              {delFile.isPending && delFile.variables === f.filename ? (
                <span className="size-3.5 animate-spin rounded-full border-2 border-border border-t-olive" />
              ) : (
                <button type="button" className="rounded p-1 text-muted-foreground opacity-0 hover:text-destructive group-hover:opacity-100"
                  disabled={delFile.isPending}
                  onClick={async () => { if (await confirm({ title: t("delete_file"), description: t("confirm_delete_file", { name: f.filename, n: f.tables.length }), actionLabel: t("delete"), destructive: true })) delFile.mutate(f.filename); }}><Trash2 className="size-3.5" /></button>
              )}
            </li>
          ))}
        </ul>
      </Section>

      <Section icon={<Palette className="size-4" />} title={t("brand_title")} count={state.brand.length} defaultOpen={state.brand.length > 0}>
        <div onClick={() => brandInput.current?.click()} className="cursor-pointer rounded-xl border border-dashed border-border p-3 text-center text-xs text-muted-foreground hover:border-olive">
          ＋ PNG / JPG / SVG / PDF
          <input ref={brandInput} type="file" multiple accept=".pdf,.png,.jpg,.jpeg,.svg" hidden onChange={(e) => uploadBrand(e.target.files)} />
        </div>
        {(state.brand_colors.length > 0 || state.brand_fonts.length > 0) && (
          <div className="flex flex-wrap items-center gap-2">
            {state.brand_colors.map((c) => <span key={c} title={c} className="size-7 rounded-lg border border-white/15" style={{ background: c }} />)}
            {state.brand_fonts.map((f) => <span key={f} className="rounded-full border border-border px-2.5 py-1 text-xs">{f}</span>)}
          </div>
        )}
        <ul className="flex max-h-64 flex-col gap-2 overflow-auto">
          {state.brand.map((f) => (
            <li key={f} className="group flex items-center gap-3 rounded-lg border border-border bg-secondary/40 px-3 py-2 text-sm">
              {/\.(png|jpe?g|svg)$/i.test(f) && <img src={p(pid, `/brand/file/${encodeURIComponent(f)}`)} alt="" className="h-7 max-w-24 object-contain" />}
              <span className="flex-1 truncate">{f}</span>
              <button type="button" className="rounded p-1 text-muted-foreground opacity-0 hover:text-destructive group-hover:opacity-100" onClick={() => delBrand.mutate(f)}><Trash2 className="size-3.5" /></button>
            </li>
          ))}
        </ul>
      </Section>

      <Section icon={<Brain className="size-4" />} title={t("notes_title")} count={state.notes.length}>
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (note.trim()) addNote.mutate(note.trim()); }}>
          <Input placeholder={t("note_ph")} value={note} onChange={(e) => setNote(e.target.value)} />
          <Button type="submit" variant="outline" disabled={!note.trim()} title={t("add")}><Plus className="size-4" /></Button>
        </form>
        <ul className="flex max-h-96 flex-col gap-2 overflow-auto">
          {state.notes.map((n, i) => (
            <li key={i} className="group flex items-start gap-2 rounded-lg border border-border bg-secondary/40 px-3 py-2 text-[13px] leading-relaxed">
              <span className="mt-1.5 text-[8px] text-olive">◆</span>
              <span className="flex-1">{n}</span>
              <button type="button" className="rounded p-1 text-muted-foreground opacity-0 hover:text-destructive group-hover:opacity-100" onClick={() => delNote.mutate(i)}><Trash2 className="size-3.5" /></button>
            </li>
          ))}
        </ul>
      </Section>
      <Card className="border-destructive/30 p-5">
        <div className="flex flex-wrap items-center gap-3">
          <span className="inline-flex size-9 items-center justify-center rounded-xl border border-destructive/30 bg-destructive/10 text-destructive">
            <AlertTriangle className="size-4" />
          </span>
          <span className="flex-1">
            <h3 className="text-[14.5px] font-bold">{t("clear_project")}</h3>
            <div className="text-xs text-muted-foreground">{t("clear_project_hint")}</div>
          </span>
          <Button variant="outline" disabled={clearProject.isPending}
            className="border-destructive/40 text-destructive hover:bg-destructive/10 hover:text-destructive"
            onClick={async () => {
              if (await confirm({
                title: t("clear_project"),
                description: t("clear_project_confirm"),
                actionLabel: t("clear_project"),
                destructive: true,
                confirmText: state.name,
                confirmHint: t("type_project_name", { name: state.name }),
              })) clearProject.mutate();
            }}>
            {clearProject.isPending ? t("uploading") : t("clear_project")}
          </Button>
        </div>
      </Card>
    </div>
  );
}
