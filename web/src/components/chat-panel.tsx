"use client";
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { endpoints, getModelPref, runJob, setModelPref, type AgentResult, type ChatMessage, type JobEvent, type Question } from "@/lib/api";
import { useT, type Key } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { MessageCircle, Send, X } from "lucide-react";

type Item = ChatMessage & { live?: JobEvent[]; started?: number; procId?: string };

export function ChatPanel({ pid, initial, open, onOpenChange, pending }: {
  pid: string; initial: ChatMessage[]; open: boolean; onOpenChange: (o: boolean) => void;
  pending?: { tables: string[] } | null;
}) {
  const t = useT();
  const qc = useQueryClient();
  const [items, setItems] = useState<Item[]>(initial);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [model, setModel] = useState(() => getModelPref(pid));
  const credits = useQuery({ queryKey: ["pres-credits", pid], queryFn: () => endpoints.credits(pid), staleTime: 60_000 });
  const maxLocked = credits.data ? !["pro", "ultra"].includes(credits.data.plan) : false;
  const costChat = credits.data?.costs?.chat?.[model];
  const costAnalysis = credits.data?.costs?.analysis?.[model];
  function pickModel(m: string) { setModel(m); setModelPref(pid, m); }
  const logRef = useRef<HTMLDivElement>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => { setItems(initial); }, [initial]);
  useEffect(() => { logRef.current?.scrollTo({ top: 1e9 }); }, [items, tick]);
  useEffect(() => { if (!busy) return; const id = setInterval(() => setTick((x) => x + 1), 1000); return () => clearInterval(id); }, [busy]);

  async function run(label: string, start: Promise<{ job_id: string } | AgentResult>) {
    setBusy(true);
    const procId = `proc-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    setItems((it) => [...it, { role: "process", text: label, live: [], started: Date.now(), procId }]);
    try {
      const res = await runJob<AgentResult>(start, (ev) => {
        setItems((it) => it.map((m) => (m.procId === procId ? { ...m, live: [...(m.live ?? []), ev].slice(-8) } : m)));
      });
      setItems((it) => [...it.filter((m) => m.procId !== procId), { role: "ai", text: res.reply || t("done"), questions: res.questions }]);
      qc.invalidateQueries({ queryKey: ["state", pid] });
    } catch (e) {
      setItems((it) => [...it.filter((m) => m.procId !== procId), { role: "ai", text: t("problem", { msg: (e as Error).message }) }]);
    } finally { setBusy(false); }
  }

  // a fresh upload opens the brief form (the user frames the analysis first)
  const lastPending = useRef<string>("");
  const [brief, setBrief] = useState<{ tables: string[] } | null>(null);
  const [ctx, setCtx] = useState("");
  const [goal, setGoal] = useState("");
  useEffect(() => {
    if (!pending) return;
    const key = pending.tables.join("|");
    if (key === lastPending.current) return;
    lastPending.current = key;
    console.info("[review] brief form for", pending.tables.length, "table(s)");
    onOpenChange(true);
    setBrief({ tables: pending.tables });
  }, [pending]);   // eslint-disable-line react-hooks/exhaustive-deps

  function send(msg: string) {
    const text = msg.trim();
    if (!text || busy) return;
    setItems((it) => [...it, { role: "user", text }]);
    setText("");
    run(t("thinking"), endpoints.chat(pid, text, model));
  }

  function startReview(tables: string[], context: string, aim: string) {
    setBrief(null);
    console.info("[review] starting, model:", model, "| context:", context.length, "| goal:", aim.length);
    run(t("thinking"), endpoints.review(pid, tables, context, aim, model));
  }

  
  return (
    <>
      {!open && (
        <button type="button" onClick={() => onOpenChange(true)}
          className="grad-olive fixed bottom-6 right-6 z-40 flex size-14 items-center justify-center rounded-full text-primary-foreground shadow-[0_10px_40px_rgba(181,211,61,0.35)] transition-transform hover:scale-105">
          <MessageCircle className="size-6" />
        </button>
      )}
      <aside
        className={`fixed bottom-4 right-4 top-[73px] z-40 flex w-[420px] max-w-[calc(100vw-2rem)] flex-col overflow-hidden rounded-2xl border border-border bg-popover/95 shadow-[0_24px_70px_rgba(0,0,0,0.45)] backdrop-blur-xl transition-all duration-300 ${open ? "translate-x-0 opacity-100" : "pointer-events-none translate-x-[110%] opacity-0"}`}
        aria-hidden={!open}
      >
        <div className="flex items-center gap-2 border-b border-border px-4 py-3">
          <MessageCircle className="size-4 text-olive" />
          <span className="text-sm font-bold">{t("chat")}</span>
          <span className="flex-1" />
          <Button variant="ghost" size="icon" onClick={() => onOpenChange(false)}><X className="size-4" /></Button>
        </div>
        <div className="border-b border-border px-4 py-2.5">
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">{t("model_label")}</span>
            <div className="inline-flex overflow-hidden rounded-lg border border-border text-[11.5px] font-bold">
              {(["standard", "max"] as const).map((m) => (
                <button key={m} type="button" disabled={m === "max" && maxLocked}
                  title={m === "max" && maxLocked ? t("model_max_locked") : ""}
                  onClick={() => pickModel(m)}
                  className={`px-2.5 py-1 transition-colors ${model === m ? "grad-olive text-primary-foreground" : "text-muted-foreground hover:text-foreground"} ${m === "max" && maxLocked ? "cursor-not-allowed opacity-40" : ""}`}>
                  {m === "standard" ? t("model_standard") : t("model_max")}
                </button>
              ))}
            </div>
            {costAnalysis != null && (
              <span className="ml-auto text-[10.5px] tabular-nums text-muted-foreground">
                {t("cost_hint", { q: costChat ?? 0, a: costAnalysis })}
              </span>
            )}
          </div>
          <div className="mt-1 text-[11px] leading-snug text-muted-foreground">
            {t((model === "max" ? "model_max_desc" : "model_standard_desc") as Key)}
          </div>
        </div>
        <div ref={logRef} className="flex-1 space-y-3 overflow-auto px-4 py-4">
          {items.map((m, i) => (
            <div key={i}>
              {m.role === "process" ? (
                <div className="overflow-hidden rounded-xl border border-olive/30 bg-olive/5 px-3 py-2 text-xs">
                  <div className="mb-1 flex items-center gap-2 font-bold text-olive">
                    <span className="size-3 animate-spin rounded-full border-2 border-border border-t-olive" />
                    {m.text} · {Math.round((Date.now() - (m.started ?? Date.now())) / 1000)}s
                  </div>
                  <ul className="space-y-0.5 text-muted-foreground">
                    {m.live?.map((ev, li) => (
                      <li key={ev.seq}
                        className={`flex min-w-0 gap-1 ${li === (m.live!.length - 1) ? "text-foreground" : "opacity-70"}`}>
                        <span className="shrink-0 text-olive">{ev.kind === "sql" ? "⌗" : ev.kind === "chart" ? "▤" : ev.kind === "note" ? "◆" : ev.kind === "error" ? "!" : "·"}</span>
                        <span className="min-w-0 flex-1 truncate">{ev.text}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : m.role === "event" ? (
                <div className="text-center text-[11px] text-muted-foreground">{m.text}</div>
              ) : (
                <div className={`max-w-[92%] whitespace-pre-wrap rounded-2xl px-3.5 py-2.5 text-[13px] leading-relaxed ${m.role === "user" ? "ml-auto grad-olive text-primary-foreground" : "bg-secondary"}`}>
                  {m.text}
                  {m.questions && m.questions.length > 0 && i === items.length - 1 && (
                    <QuestionForm questions={m.questions} onSubmit={(answer) => send(answer)} />
                  )}
                </div>
              )}
            </div>
          ))}
        {brief && (
            <div className="flex flex-col gap-2 rounded-xl border border-olive/40 bg-olive/5 p-3">
            <div className="text-[13px] font-bold">{t("brief_title", { n: brief.tables.length })}</div>
            <div className="text-[11.5px] leading-snug text-muted-foreground">{t("brief_hint")}</div>
            <label className="text-[11px] font-semibold text-muted-foreground">{t("brief_context")}
              <Textarea value={ctx} onChange={(e) => setCtx(e.target.value)} rows={3} placeholder={t("brief_context_ph")} className="mt-1 max-h-40 overflow-auto text-[13px]" />
            </label>
            <label className="text-[11px] font-semibold text-muted-foreground">{t("brief_goal")}
              <Textarea value={goal} onChange={(e) => setGoal(e.target.value)} rows={3} placeholder={t("brief_goal_ph")} className="mt-1 max-h-40 overflow-auto text-[13px]" />
            </label>
            <div className="sticky bottom-0 -mx-3 -mb-3 flex justify-end gap-2 rounded-b-xl border-t border-olive/20 bg-popover/95 px-3 py-2 backdrop-blur">
              <Button size="sm" variant="ghost" onClick={() => startReview(brief.tables, "", "")}>{t("brief_skip")}</Button>
              <Button size="sm" className="grad-olive font-bold text-primary-foreground"
                onClick={() => startReview(brief.tables, ctx.trim(), goal.trim())}>{t("brief_start")}</Button>
            </div>
          </div>
          )}
        </div>
        <form className="flex items-end gap-2 border-t border-border p-3" onSubmit={(e) => { e.preventDefault(); send(text); }}>
          <Textarea value={text} onChange={(e) => setText(e.target.value)} placeholder={t("chat_ph")} rows={2}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(text); } }}
            className="min-h-0 resize-none" disabled={busy} />
          <Button type="submit" disabled={busy || !text.trim()} title={costChat != null ? t("approx_cr", { n: costChat }) : ""}
            className="grad-olive text-primary-foreground"><Send className="size-4" /></Button>
        </form>
      </aside>
    </>
  );
}

function QuestionForm({ questions, onSubmit }: { questions: Question[]; onSubmit: (answer: string) => void }) {
  const t = useT();
  const [picked, setPicked] = useState<Record<number, Set<string>>>({});
  const [other, setOther] = useState<Record<number, string>>({});
  const toggle = (qi: number, opt: string) => setPicked((p) => {
    const s = new Set(p[qi] ?? []); s.has(opt) ? s.delete(opt) : s.add(opt); return { ...p, [qi]: s };
  });
  const compose = () => questions.map((q, qi) => {
    const parts = [...(picked[qi] ?? [])]; if (other[qi]?.trim()) parts.push(other[qi].trim());
    return parts.length ? `${q.question}\n→ ${parts.join("; ")}` : null;
  }).filter(Boolean).join("\n\n");
  return (
    <div className="mt-3 space-y-3 rounded-xl border border-border bg-card p-3 text-foreground">
      {questions.map((q, qi) => (
        <div key={qi}>
          <div className="mb-1.5 text-[13px] font-semibold">{q.question}</div>
          <div className="flex flex-wrap gap-1.5">
            {q.options.map((opt) => (
              <button key={opt} type="button" onClick={() => toggle(qi, opt)}
                className={`rounded-full border px-2.5 py-1 text-xs transition-colors ${picked[qi]?.has(opt) ? "border-olive bg-olive/15 text-foreground" : "border-border text-muted-foreground hover:text-foreground"}`}>{opt}</button>
            ))}
          </div>
          <input className="mt-1.5 w-full rounded-md border border-border bg-transparent px-2 py-1 text-xs" placeholder="…" value={other[qi] ?? ""} onChange={(e) => setOther({ ...other, [qi]: e.target.value })} />
        </div>
      ))}
      <Button size="sm" className="grad-olive text-primary-foreground" disabled={!compose()} onClick={() => onSubmit(compose())}>{t("send")}</Button>
    </div>
  );
}
