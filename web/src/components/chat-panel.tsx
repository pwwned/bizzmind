"use client";
import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { endpoints, runJob, type AgentResult, type ChatMessage, type JobEvent, type Question } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { MessageCircle, Send, X } from "lucide-react";

type Item = ChatMessage & { live?: JobEvent[]; started?: number };

export function ChatPanel({ pid, initial, open, onOpenChange, pending }: {
  pid: string; initial: ChatMessage[]; open: boolean; onOpenChange: (o: boolean) => void;
  pending?: { tables: string[] } | null;
}) {
  const t = useT();
  const qc = useQueryClient();
  const [items, setItems] = useState<Item[]>(initial);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => { setItems(initial); }, [initial]);
  useEffect(() => { logRef.current?.scrollTo({ top: 1e9 }); }, [items, tick]);
  useEffect(() => { if (!busy) return; const id = setInterval(() => setTick((x) => x + 1), 1000); return () => clearInterval(id); }, [busy]);

  async function run(label: string, start: Promise<{ job_id: string } | AgentResult>) {
    setBusy(true);
    const proc: Item = { role: "process", text: label, live: [], started: Date.now() };
    setItems((it) => [...it, proc]);
    try {
      const res = await runJob<AgentResult>(start, (ev) => {
        setItems((it) => it.map((m) => (m === proc ? { ...m, live: [...(m.live ?? []), ev].slice(-7) } : m)));
      });
      setItems((it) => [...it.filter((m) => m !== proc), { role: "ai", text: res.reply || t("done"), questions: res.questions }]);
      qc.invalidateQueries({ queryKey: ["state", pid] });
    } catch (e) {
      setItems((it) => [...it.filter((m) => m !== proc), { role: "ai", text: t("problem", { msg: (e as Error).message }) }]);
    } finally { setBusy(false); }
  }

  // a fresh upload triggers the interview
  const lastPending = useRef<string>("");
  useEffect(() => {
    if (!pending) return;
    const key = pending.tables.join("|");
    if (key === lastPending.current) return;
    lastPending.current = key;
    onOpenChange(true);
    run(t("thinking"), endpoints.review(pid, pending.tables, "", ""));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending]);

  function send(msg: string) {
    if (!msg.trim() || busy) return;
    setItems((it) => [...it, { role: "user", text: msg }]);
    setText("");
    run(t("thinking"), endpoints.chat(pid, msg));
  }

  return (
    <>
      {!open && (
        <button type="button" onClick={() => onOpenChange(true)}
          className="grad-olive fixed bottom-6 right-6 z-40 flex size-14 items-center justify-center rounded-full text-primary-foreground shadow-[0_10px_40px_rgba(181,211,61,0.35)] transition-transform hover:scale-105">
          <MessageCircle className="size-6" />
        </button>
      )}
      <aside className={`fixed bottom-0 right-0 top-[57px] z-30 flex w-[420px] max-w-full flex-col border-l border-border bg-popover/95 backdrop-blur-xl transition-transform ${open ? "translate-x-0" : "translate-x-full"}`}>
        <div className="flex items-center gap-2 border-b border-border px-4 py-3">
          <MessageCircle className="size-4 text-olive" />
          <span className="text-sm font-bold">{t("chat")}</span>
          <span className="flex-1" />
          <Button variant="ghost" size="icon" onClick={() => onOpenChange(false)}><X className="size-4" /></Button>
        </div>
        <div ref={logRef} className="flex-1 space-y-3 overflow-auto px-4 py-4">
          {items.map((m, i) => (
            <div key={i}>
              {m.role === "process" ? (
                <div className="rounded-xl border border-olive/30 bg-olive/5 px-3 py-2 text-xs">
                  <div className="mb-1 flex items-center gap-2 font-bold text-olive">
                    <span className="size-3 animate-spin rounded-full border-2 border-border border-t-olive" />
                    {m.text} · {Math.round((Date.now() - (m.started ?? Date.now())) / 1000)}s
                  </div>
                  <ul className="space-y-0.5 text-muted-foreground">{m.live?.map((ev) => <li key={ev.seq} className="truncate">{ev.text}</li>)}</ul>
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
        </div>
        <form className="flex items-end gap-2 border-t border-border p-3" onSubmit={(e) => { e.preventDefault(); send(text); }}>
          <Textarea value={text} onChange={(e) => setText(e.target.value)} placeholder={t("chat_ph")} rows={2}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(text); } }}
            className="min-h-0 resize-none" disabled={busy} />
          <Button type="submit" disabled={busy || !text.trim()} className="grad-olive text-primary-foreground"><Send className="size-4" /></Button>
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
