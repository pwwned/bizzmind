"use client";
/* Presentation dialog: the AI writes the deck content from the dashboard,
   charts are rendered to PNGs, and Gamma builds an editable presentation.
   Mirrors the old UI's gmodal, on shadcn primitives. */
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, endpoints, p as apiPath, runJob, type Chart, type I18nInfo } from "@/lib/api";

import { localeOf, useLang, useT } from "@/lib/i18n";
import { buildOption, PALETTES, useLabelMaps } from "@/components/chart-card";
import { seriesPalette, themeScore, type GammaTheme } from "@/lib/deck-theme";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Presentation, ExternalLink, Download, Sparkles } from "lucide-react";

interface GammaOptions {
  enabled: boolean; public_images?: boolean; themes?: GammaTheme[];
  text_modes?: { id: string; label: string; hint: string }[];
  image_sources?: { id: string; label: string }[];
  dimensions?: string[]; export_as?: string[];
  languages?: { id: string; label: string }[]; default_language?: string;
}
interface DeckSlideRef { chart_id: number; headline?: string; narrative?: string }
interface DeckSpec {
  title?: string; subtitle?: string;
  sections?: { heading?: string; slides?: DeckSlideRef[] }[];
  takeaways?: { title?: string; text?: string }[];
  gamma?: { audience?: string; tone?: string; emphasis?: string[]; instructions?: string;
            text_mode?: string; image_source?: string; num_cards?: number };
}
interface GammaStatus { status: string; gamma_url?: string; export_url?: string; error?: unknown; credits?: { deducted?: number; remaining?: number } }
type Slide = { heading: string; title: string; narrative: string; image?: string; columns?: string[]; rows?: unknown[][] };

const specCache = new Map<string, DeckSpec>();

function scaleFonts(node: unknown, k: number) {
  if (Array.isArray(node)) { node.forEach((n) => scaleFonts(n, k)); return; }
  if (!node || typeof node !== "object") return;
  const o = node as Record<string, unknown>;
  for (const key of Object.keys(o)) {
    if (key === "fontSize" && typeof o[key] === "number") o[key] = Math.round((o[key] as number) * k);
    else scaleFonts(o[key], k);
  }
}

export function PresentationDialog({ pid, name, charts, i18n, brandPrimary, brandColors }: {
  pid: string; name: string; charts: Chart[]; i18n?: I18nInfo; brandPrimary?: string; brandColors?: string[];
}) {
  const t = useT();
  const { lang } = useLang();
  const { L, LV } = useLabelMaps(i18n);
  const [open, setOpen] = useState(false);
  const [phase, setPhase] = useState<"idle" | "spec" | "rendering" | "building">("idle");
  const [elapsed, setElapsed] = useState(0);
  const [specEvent, setSpecEvent] = useState("");
  const [spec, setSpec] = useState<DeckSpec | null>(null);
  const [specFailed, setSpecFailed] = useState(false);
  const [themeId, setThemeId] = useState<string | null>(null);
  const [themeQ, setThemeQ] = useState("");
  const [textMode, setTextMode] = useState("preserve");
  const [imageSource, setImageSource] = useState("noImages");
  const [numCards, setNumCards] = useState("");
  const [dims, setDims] = useState("16x9");
  const [exportAs, setExportAs] = useState("pdf");
  const [deckLang, setDeckLang] = useState(lang);
  const [extra, setExtra] = useState("");
  const [warnings, setWarnings] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [result, setResult] = useState<GammaStatus | null>(null);
  const [resultGid, setResultGid] = useState<string | null>(null);
  const specKey = pid + "|" + charts.map((c) => c.id + ":" + c.title).join("|");
  const busy = phase !== "idle";
  const generating = phase === "rendering" || phase === "building";
  const lockRef = useRef(false);
  lockRef.current = generating;

  const qc = useQueryClient();
  const credits = useQuery({
    queryKey: ["pres-credits", pid],
    queryFn: () => endpoints.credits(pid),
    enabled: open,
  });
  const remaining = credits.data?.remaining;
  const opts = useQuery({
    queryKey: ["gamma-options", lang],
    queryFn: () => api<GammaOptions>("/api/pres/options"),
    enabled: open,
    staleTime: 30 * 60_000,
  });
  const o = opts.data;

  useEffect(() => {
    if (!busy) return;
    setElapsed(0);
    const id = setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, [busy, phase]);

  function applySpec(s: DeckSpec) {
    setSpec(s); setSpecFailed(false);
    const g = s.gamma ?? {};
    setExtra(g.instructions ?? "");
    if (g.text_mode && ["preserve", "condense", "generate"].includes(g.text_mode)) setTextMode(g.text_mode);
    if (g.image_source) setImageSource(g.image_source);
    if (g.num_cards) setNumCards(String(g.num_cards));
  }

  async function ensureSpec(force = false) {
    if (!force && specCache.has(specKey)) { applySpec(specCache.get(specKey)!); return; }
    setPhase("spec"); setSpecEvent("");
    try {
      const d = await runJob<{ spec: DeckSpec }>(endpoints.deck(pid) as Promise<{ job_id: string } | { spec: DeckSpec }>, (ev) => setSpecEvent(ev.text));
      specCache.set(specKey, d.spec);
      applySpec(d.spec);
    } catch {
      // no AI available (or it failed) — fall back to dashboard titles & insights
      setSpec(null); setSpecFailed(true); setExtra("");
    } finally { setPhase("idle"); }
  }

  useEffect(() => {
    if (!open) return;
    setResult(null); setError(""); setWarnings([]);
    setDeckLang(lang);
    void ensureSpec();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // Gamma's default theme is the generic one; the theme decides almost the whole
  // look of a deck. Start on the best brand match instead, and never override a
  // choice the user has made — including deliberately clearing it.
  const themePicked = useRef(false);
  useEffect(() => {
    const list = o?.themes;
    if (themePicked.current || !list?.length) return;
    const best = list.slice().sort((a, b) =>
      themeScore(b, brandPrimary ?? "") - themeScore(a, brandPrimary ?? "") || a.name.localeCompare(b.name))[0];
    if (best) setThemeId(best.id);
  }, [o?.themes, brandPrimary]);

  async function chartPng(ch: Chart): Promise<string | undefined> {
    const echarts = await import("echarts");
    const cats = ch.rows.map((r) => String(r[ch.x_field] ?? ""));
    const horizontal = ch.chart_type === "bar" && (cats.length > 8 || cats.some((c) => c.length > 14));
    const w = 1040, h = horizontal ? Math.min(900, Math.max(480, ch.rows.length * 46 + 140)) : 560;
    const div = document.createElement("div");
    div.style.cssText = `position:fixed;left:-4000px;top:0;width:${w}px;height:${h}px;`;
    document.body.appendChild(div);
    try {
      const inst = echarts.init(div);
      // The deck belongs to the client, so its charts carry the client's brand,
      // not the product's own olive. Falls back when there is no brand book.
      const pal = { ...PALETTES.light, SERIES: seriesPalette(brandColors, PALETTES.light.SERIES) };
      const opt = buildOption(ch, L, LV, pal) as Record<string, unknown>;
      opt.backgroundColor = "#ffffff"; opt.animation = false;
      scaleFonts(opt, 1.8);
      inst.setOption(opt);
      await new Promise((r) => setTimeout(r, 120));
      const url = inst.getDataURL({ type: "png", pixelRatio: 2, backgroundColor: "#ffffff" });
      inst.dispose();
      return url;
    } catch { return undefined; }
    finally { div.remove(); }
  }

  async function collectSlides(s: DeckSpec): Promise<Slide[]> {
    const byId = new Map(charts.map((c) => [c.id, c]));
    const slides: Slide[] = [], seen = new Set<number>();
    const push = async (ch: Chart, heading = "", title = "", narrative = "") => {
      seen.add(ch.id);
      const sl: Slide = { heading, title: title || ch.title, narrative: narrative || ch.insight || "" };
      const cols = [ch.x_field, ...(ch.y_fields ?? []).filter((y) => y !== ch.x_field)];
      if (ch.chart_type === "table") {
        sl.columns = cols.map(L);
        sl.rows = ch.rows.slice(0, 12).map((r) => cols.map((c) => LV(r[c])));
      } else {
        sl.image = await chartPng(ch);
        if (ch.rows.length) {
          sl.columns = cols.map(L);
          sl.rows = ch.rows.slice(0, 12).map((r) => cols.map((c) => LV(r[c])));
        }
      }
      slides.push(sl);
    };
    for (const sec of s.sections ?? [])
      for (const ref of sec.slides ?? []) {
        const ch = byId.get(ref.chart_id);
        if (ch) await push(ch, sec.heading ?? "", ref.headline ?? "", ref.narrative ?? "");
      }
    for (const ch of charts) if (!seen.has(ch.id)) await push(ch);
    return slides;
  }

  async function generate() {
    setError(""); setResult(null); setWarnings([]);
    try {
      setPhase("rendering");
      const s = spec ?? {};
      const slides = await collectSlides(s);
      const body = {
        title: s.title || name, subtitle: s.subtitle || "", slides, takeaways: s.takeaways ?? [],
        theme_id: themeId, text_mode: textMode,
        num_cards: parseInt(numCards, 10) || null,
        image_source: imageSource, dimensions: dims, export_as: exportAs,
        language: deckLang, extra_instructions: extra.trim(),
      };
      const start = await api<{ generation_id: string; warnings?: string[] }>(apiPath(pid, "/pres"),
        { method: "POST", body: JSON.stringify(body) });
      setWarnings(start.warnings ?? []);
      setResultGid(start.generation_id);
      setPhase("building");
      const t0 = Date.now();
      for (;;) {
        await new Promise((r) => setTimeout(r, 5000));
        const st = await api<GammaStatus>(`/api/pres/status/${encodeURIComponent(start.generation_id)}`);
        if (st.status === "completed") {
          setResult(st);
          qc.invalidateQueries({ queryKey: ["pres-credits", pid] });
          toast.success(t("done_in", { s: Math.round((Date.now() - t0) / 1000) }));
          break;
        }
        if (st.status === "failed") {
          const e = st.error as { message?: string } | string | undefined;
          throw new Error((typeof e === "object" ? e?.message : e) || t("gamma_error"));
        }
        if (Date.now() - t0 > 8 * 60_000) throw new Error(t("gamma_timeout"));
      }
    } catch (e) {
      setError(t("generation_failed", { msg: (e as Error).message }));
    } finally { setPhase("idle"); }
  }

  const themes = (o?.themes ?? [])
    .slice()
    .sort((a, b) => themeScore(b, brandPrimary ?? "") - themeScore(a, brandPrimary ?? "") || a.name.localeCompare(b.name))
    .filter((th) => {
      const hay = (th.name + " " + (th.colorKeywords ?? []).join(" ") + " " + (th.toneKeywords ?? []).join(" ")).toLowerCase();
      return !themeQ.trim() || hay.includes(themeQ.toLowerCase().trim());
    })
    .slice(0, 24);
  const g = spec?.gamma;
  const selectCls = "h-9 rounded-lg border border-border bg-secondary/40 px-2.5 text-[13px] outline-none focus:border-olive";

  return (
    <>
      <Button variant="outline" size="sm" className="ml-auto" disabled={charts.length === 0} onClick={() => setOpen(true)}>
        <Presentation className="size-4" />{t("presentation")}
      </Button>
      <Dialog open={open} onOpenChange={(v) => { if (!lockRef.current) setOpen(v); }}>
      <DialogContent className="flex max-h-[88vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-2xl">
        <DialogHeader className="border-b border-border px-6 py-4">
          <DialogTitle>{t("presentation")}</DialogTitle>
          <DialogDescription className="text-[12.5px] leading-relaxed">{t("g_sub")}</DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-5 overflow-y-auto px-6 py-5">
          {opts.isLoading && <div className="text-sm text-muted-foreground">{t("loading_project")}</div>}
          {o && !o.enabled && <div className="rounded-lg border border-border bg-secondary/40 p-3 text-sm text-muted-foreground">{t("gamma_not_configured")}</div>}

          {o?.enabled && (
            <>
              {/* AI brief */}
              <section className="rounded-xl border border-olive/25 bg-olive/5 p-4">
                <div className="mb-2 flex items-center gap-2">
                  <Sparkles className="size-4 text-olive" />
                  <span className="text-[12px] font-bold uppercase tracking-wider text-olive">{t("g_brief")}</span>
                  <Button variant="ghost" size="sm" className="ml-auto h-7 text-xs" disabled={busy} onClick={() => void ensureSpec(true)}>{t("g_rewrite")}</Button>
                </div>
                {phase === "spec" ? (
                  <div className="flex items-center gap-2.5 text-[13px] text-muted-foreground">
                    <span className="size-4 shrink-0 animate-spin rounded-full border-2 border-border border-t-olive" />
                    {t("writing_deck")} · {elapsed}s{specEvent ? ` — ${specEvent}` : ""}
                  </div>
                ) : g?.instructions ? (
                  <div className="flex flex-col gap-1 text-[13px] leading-relaxed">
                    {g.audience && <div><b className="text-muted-foreground">{t("audience")}:</b> {g.audience}</div>}
                    {g.tone && <div><b className="text-muted-foreground">{t("tone_label")}:</b> {g.tone}</div>}
                    {!!g.emphasis?.length && <div><b className="text-muted-foreground">{t("emphasis")}:</b> {g.emphasis.join(" · ")}</div>}
                  </div>
                ) : (
                  <div className="text-[13px] text-muted-foreground">{specFailed ? t("brief_missing") : ""}</div>
                )}
              </section>

              {/* theme */}
              <section>
                <div className="mb-2 flex items-center gap-3">
                  <span className="text-[12px] font-bold uppercase tracking-wider text-muted-foreground">{t("g_theme")}</span>
                  <Input value={themeQ} onChange={(e) => setThemeQ(e.target.value)} placeholder={t("g_theme_ph")} className="h-8 max-w-xs text-xs" />
                </div>
                <div className="grid max-h-44 grid-cols-2 gap-2 overflow-y-auto pr-1 sm:grid-cols-3">
                  {themes.map((th) => (
                    <button key={th.id} type="button"
                      onClick={() => { themePicked.current = true; setThemeId(themeId === th.id ? null : th.id); }}
                      className={`rounded-lg border px-2.5 py-2 text-left transition-colors ${themeId === th.id ? "border-olive bg-olive/10" : "border-border bg-secondary/40 hover:border-olive/50"}`}>
                      <span className="flex items-center gap-1.5">
                        {th.type === "custom" && <span className="rounded bg-olive/20 px-1 text-[9px] font-extrabold text-olive">{t("theme_custom_tag")}</span>}
                        <b className="truncate text-[12.5px]">{th.name}</b>
                      </span>
                      <span className="block truncate text-[10.5px] text-muted-foreground">{(th.colorKeywords ?? []).slice(0, 4).join(", ")}</span>
                    </button>
                  ))}
                </div>
                {!themeId && <div className="mt-1.5 text-[11px] text-muted-foreground">{t("theme_none")}</div>}
              </section>

              {/* Gamma controls */}
              <section className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3">
                <label className="flex flex-col gap-1 text-[11px] font-semibold text-muted-foreground">{t("g_text")}
                  <select className={selectCls} value={textMode} onChange={(e) => setTextMode(e.target.value)}>
                    {(o.text_modes ?? []).map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
                  </select>
                </label>
                <label className="flex flex-col gap-1 text-[11px] font-semibold text-muted-foreground">{t("g_images")}
                  <select className={selectCls} value={imageSource} onChange={(e) => setImageSource(e.target.value)}>
                    {(o.image_sources ?? []).map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
                  </select>
                </label>
                <label className="flex flex-col gap-1 text-[11px] font-semibold text-muted-foreground">{t("g_cards")}
                  <Input type="number" min={1} max={75} value={numCards} onChange={(e) => setNumCards(e.target.value)} placeholder={t("g_cards_ph")} className="h-9 text-[13px]" />
                </label>
                <label className="flex flex-col gap-1 text-[11px] font-semibold text-muted-foreground">{t("g_dims")}
                  <select className={selectCls} value={dims} onChange={(e) => setDims(e.target.value)}>
                    {(o.dimensions ?? []).map((d) => <option key={d} value={d}>{d}</option>)}
                  </select>
                </label>
                <label className="flex flex-col gap-1 text-[11px] font-semibold text-muted-foreground">{t("g_format")}
                  <select className={selectCls} value={exportAs} onChange={(e) => setExportAs(e.target.value)}>
                    {(o.export_as ?? []).map((d) => <option key={d} value={d}>{d.toUpperCase()}</option>)}
                  </select>
                </label>
                <label className="flex flex-col gap-1 text-[11px] font-semibold text-muted-foreground">{t("g_lang")}
                  <select className={selectCls} value={deckLang} onChange={(e) => setDeckLang(e.target.value as typeof deckLang)}>
                    {(o.languages ?? []).map((d) => <option key={d.id} value={d.id}>{d.label}</option>)}
                  </select>
                </label>
              </section>

              {/* extra instructions */}
              <section>
                <div className="mb-1.5 text-[12px] font-bold uppercase tracking-wider text-muted-foreground">{t("g_extra")}</div>
                <Textarea value={extra} onChange={(e) => setExtra(e.target.value)} placeholder={t("g_extra_ph")} rows={3} className="text-[13px]" />
                <div className="mt-1 text-[11px] text-muted-foreground">{t("g_extra_hint")}</div>
              </section>

              {/* progress / result */}
              {(phase === "rendering" || phase === "building") && (
                <div className="flex items-center gap-2.5 rounded-lg border border-border bg-secondary/40 p-3 text-[13px]">
                  <span className="size-4 shrink-0 animate-spin rounded-full border-2 border-border border-t-olive" />
                  {phase === "rendering" ? t("rendering_sending") : t("gamma_building", { s: elapsed })}
                </div>
              )}
              {warnings.map((w, i) => <div key={i} className="rounded-lg border border-yellow-600/40 bg-yellow-500/10 p-2.5 text-[12.5px] text-yellow-600 dark:text-yellow-400">{w}</div>)}
              {error && <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-2.5 text-[12.5px] text-destructive">{error}</div>}
              {result && (
                <div className="flex flex-col gap-2 rounded-xl border border-olive/40 bg-olive/10 p-4">
                  <div className="flex flex-wrap items-center gap-3">
                    {result.gamma_url && (
                      <a href={result.gamma_url} target="_blank" rel="noopener" className="inline-flex items-center gap-1.5 font-bold text-olive hover:underline">
                        <ExternalLink className="size-4" />{t("open_in_gamma")}
                      </a>
                    )}
                    {result.gamma_url && <span className="text-[12px] text-muted-foreground">{t("editable")}</span>}
                    {result.export_url && (
                      <a href={`/api/pres/file/${encodeURIComponent(resultGid ?? "")}`} className="inline-flex items-center gap-1.5 font-bold text-olive hover:underline">
                        <Download className="size-4" />{t("download_fmt", { fmt: exportAs.toUpperCase() })}
                      </a>
                    )}
                  </div>
                  {result.credits?.deducted != null && <div className="text-[11px] text-muted-foreground">{t("credits_line", { used: result.credits.deducted })}</div>}
                </div>
              )}
            </>
          )}
        </div>

        <DialogFooter className="border-t border-border px-6 py-4 sm:items-center">
          {remaining != null && (
            <span className="mr-auto flex flex-col gap-0.5">
              <span className={`text-[12px] ${remaining <= 0 ? "font-semibold text-destructive" : "text-muted-foreground"}`}>
                {remaining <= 0 ? t("pres_no_credits") : t("credits_left", { n: remaining.toLocaleString(localeOf(lang)) })}
              </span>
              {remaining > 0 && credits.data?.expensive && (
                <span className="text-[11px] font-semibold text-amber-700 dark:text-amber-300">{t("cost_warn")}</span>
              )}
            </span>
          )}
          <Button variant="ghost" disabled={generating} onClick={() => setOpen(false)}>{t("cancel")}</Button>
          <Button className="grad-olive font-bold text-primary-foreground hover:opacity-90"
            disabled={busy || !o?.enabled || (remaining != null && remaining <= 0)}
            onClick={() => void generate()}>
            {generating ? t("generating") : result ? t("generate_again") : t("generate")}
          </Button>
        </DialogFooter>
      </DialogContent>
      </Dialog>
    </>
  );
}
