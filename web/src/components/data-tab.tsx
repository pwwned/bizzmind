"use client";
import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, p as apiPath } from "@/lib/api";
import { endpoints, type ProjectState } from "@/lib/api";
import { useLang, useT, localeOf } from "@/lib/i18n";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight, Table2, Eye } from "lucide-react";

export function DataTab({ pid, state }: { pid: string; state: ProjectState }) {
  const t = useT();
  const { lang } = useLang();
  const qc = useQueryClient();
  const [table, setTable] = useState<string | null>(null);
  const [editing, setEditing] = useState<{ rid: string; col: string; value: string } | null>(null);
  const [saving, setSaving] = useState(false);

  async function saveCell() {
    if (!editing || !table) return;
    setSaving(true);
    try {
      await api(apiPath(pid, `/table/${encodeURIComponent(table)}/cell`), {
        method: "POST", body: JSON.stringify({ rowid: editing.rid, column: editing.col, value: editing.value }),
      });
      setEditing(null);
      await qc.invalidateQueries({ queryKey: ["rows", pid, table] });
      qc.invalidateQueries({ queryKey: ["state", pid] });     // charts reflect the change
      qc.invalidateQueries({ queryKey: ["refresh", pid] });
    } catch (e) { toast.error((e as Error).message); }
    finally { setSaving(false); }
  }
  const [q, setQ] = useState("");
  const [qDebounced, setQDebounced] = useState("");
  const [offset, setOffset] = useState(0);
  const [sort, setSort] = useState<{ col: string; dir: "asc" | "desc" } | null>(null);
  const limit = 100;

  useEffect(() => { const id = setTimeout(() => { setQDebounced(q); setOffset(0); }, 300); return () => clearTimeout(id); }, [q]);
  useEffect(() => { if (!table && state.tables.length) setTable(state.tables[0].table); }, [state.tables, table]);
  useEffect(() => { setOffset(0); setSort(null); setQ(""); }, [table]);

  const params = new URLSearchParams({ offset: String(offset), limit: String(limit), q: qDebounced, sort: sort?.col ?? "", dir: sort?.dir ?? "asc" });
  const rows = useQuery({
    queryKey: ["rows", pid, table, params.toString()],
    queryFn: () => endpoints.rows(pid, table!, params),
    enabled: !!table,
    placeholderData: (prev) => prev,
  });

  const info = state.tables.find((x) => x.table === table);

  return (
    <div className="flex min-h-0 flex-1 gap-5">
      <aside className="w-60 shrink-0 overflow-auto">
        <div className="mb-2 px-1.5 text-[11px] font-bold uppercase tracking-wider text-muted-foreground">{t("tables_title")}</div>
        {state.tables.map((tb) => (
          <button key={tb.table} type="button" onClick={() => setTable(tb.table)}
            className={`mb-1 flex w-full items-start gap-2 rounded-lg px-2.5 py-2 text-left text-[13px] transition-colors ${table === tb.table ? "bg-olive/10 text-foreground ring-1 ring-olive/40" : "text-muted-foreground hover:bg-secondary"}`}>
            {tb.kind === "view" ? <Eye className="mt-0.5 size-3.5 shrink-0 text-olive" /> : <Table2 className="mt-0.5 size-3.5 shrink-0 text-olive" />}
            <span className="min-w-0">
              <span className="block truncate font-medium" title={tb.table}>{tb.table}</span>
              <span className="text-[11px] text-muted-foreground">{tb.rows.toLocaleString(localeOf(lang))} {t("rows")} · {tb.columns.length} {t("cols")}</span>
            </span>
          </button>
        ))}
      </aside>

      <section className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-2xl border border-border bg-card">
        {!table ? (
          <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">{t("pick_table")}</div>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
              <div className="min-w-0 flex-1">
                <h3 className="truncate font-bold">{table}</h3>
                {info && <div className="text-xs text-muted-foreground">{info.rows.toLocaleString(localeOf(lang))} {t("rows")} · {info.columns.length} {t("cols")}{info.description ? ` · ${info.description}` : ""}</div>}
              </div>
              <Input placeholder={t("search_table")} value={q} onChange={(e) => setQ(e.target.value)} className="w-64" />
              <div className="flex items-center gap-1 text-xs text-muted-foreground">
                <Button variant="ghost" size="icon" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}><ChevronLeft className="size-4" /></Button>
                <span className="tabular-nums">{rows.data ? `${rows.data.total ? offset + 1 : 0}–${Math.min(offset + limit, rows.data.total)} ${t("of")} ${rows.data.total.toLocaleString(localeOf(lang))}` : "…"}</span>
                <Button variant="ghost" size="icon" disabled={!rows.data || offset + limit >= rows.data.total} onClick={() => setOffset(offset + limit)}><ChevronRight className="size-4" /></Button>
              </div>
            </div>
            <div className="border-b border-border px-4 py-1.5 text-[11px] text-muted-foreground">{t("edit_hint")}</div>
            <div className={`flex-1 overflow-auto ${rows.isFetching ? "opacity-60" : ""}`}>
              <table className="w-max min-w-full border-collapse text-[12.5px]">
                <thead className="sticky top-0 z-10 bg-card">
                  <tr>
                    {rows.data?.columns.map((c) => (
                      <th key={c.name} onClick={() => setSort(sort?.col === c.name ? { col: c.name, dir: sort.dir === "asc" ? "desc" : "asc" } : { col: c.name, dir: "asc" })}
                        className="cursor-pointer select-none whitespace-nowrap px-3 py-2 text-left text-[10.5px] font-bold uppercase tracking-wider text-muted-foreground hover:text-foreground">
                        {c.name.replace(/_/g, " ")}{sort?.col === c.name ? (sort.dir === "asc" ? " ↑" : " ↓") : ""}
                        <span className="block text-[9px] font-semibold normal-case tracking-normal text-olive/70">{c.type.toLowerCase()}</span>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.data?.rows.map((r, i) => (
                    <tr key={String(r.__rid ?? i)} className="border-t border-border/60 hover:bg-secondary/40">
                      {rows.data!.columns.map((c) => {
                        const v = r[c.name];
                        const rid = String(r.__rid ?? "");
                        const isEditing = editing && editing.rid === rid && editing.col === c.name;
                        const isView = (state.tables.find((x) => x.table === table) || {}).kind === "view";
                        return (
                          <td key={c.name}
                            className={`max-w-[360px] px-3 py-1.5 ${typeof v === "number" ? "text-right tabular-nums" : ""} ${isView ? "" : "cursor-text hover:bg-olive/10"} ${isEditing ? "bg-olive/10 ring-1 ring-olive" : "truncate"}`}
                            title={v == null ? "" : String(v)}
                            onClick={() => { if (!isView && !isEditing) setEditing({ rid, col: c.name, value: v == null ? "" : String(v) }); }}>
                            {isEditing ? (
                              <input autoFocus value={editing.value} disabled={saving}
                                onChange={(e) => setEditing({ ...editing, value: e.target.value })}
                                onKeyDown={(e) => { if (e.key === "Enter") saveCell(); if (e.key === "Escape") setEditing(null); }}
                                onBlur={() => { if (!saving) saveCell(); }}
                                className="w-full min-w-[80px] bg-transparent outline-none" />
                            ) : (v == null ? "" : String(v))}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
