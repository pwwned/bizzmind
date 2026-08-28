"use client";
/* Usage: credit balance, spend breakdown, price list, packs, plans. */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { endpoints, type Account } from "@/lib/api";
import { getPaddle } from "@/lib/paddle";
import { PACK_PRICE_IDS, TIERS } from "@/lib/tiers";
import { useConfirm } from "@/components/confirm-dialog";
import { localeOf, useLang, useT, type Key } from "@/lib/i18n";
import { AppHeader } from "@/components/app-header";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import Link from "next/link";
import { BarChart3, Blocks, Check, MessageSquare, Presentation, RefreshCcw } from "lucide-react";

const KIND_META: Record<string, { icon: React.ReactNode; key: Key }> = {
  analysis: { icon: <BarChart3 className="size-4" />, key: "kind_analysis" },
  chat: { icon: <MessageSquare className="size-4" />, key: "kind_chat" },
  presentation: { icon: <Presentation className="size-4" />, key: "kind_presentation" },
  app: { icon: <Blocks className="size-4" />, key: "kind_app" },
};

export function UsageContent() {
  const t = useT();
  const { lang } = useLang();
  const loc = localeOf(lang);
  const qc = useQueryClient();
  const acc = useQuery({ queryKey: ["account"], queryFn: endpoints.account });
  const sub = useQuery({ queryKey: ["subscription"], queryFn: endpoints.subscription });
  const confirm = useConfirm();
  const [cycle, setCycle] = useState<"month" | "year">("month");
  const change = useMutation({
    mutationFn: (v: { plan: string; interval: string }) => endpoints.subChange(v.plan, v.interval),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["subscription"] });
      qc.invalidateQueries({ queryKey: ["account"] });
      toast.success(t("plan_changed"));
    },
    onError: (e: Error) => toast.error(e.message),
  });
  async function openCheckout(priceId: string | undefined) {
    try {
      if (!priceId) { toast.error(t("pricing_not_configured")); return; }
      const paddle = await getPaddle();
      if (!paddle) throw new Error("checkout failed to load");
      paddle.Checkout.open({
        items: [{ priceId, quantity: 1 }],
        ...(a?.email ? { customer: { email: a.email } } : {}),
        ...(a?.org_id ? { customData: { org_id: a.org_id } } : {}),
        settings: { displayMode: "overlay", variant: "one-page", successUrl: `${window.location.origin}/welcome`, locale: lang },
      });
    } catch (e) { toast.error((e as Error).message); }
  }
  const subscribeNow = (planKey: string) => openCheckout(TIERS.find((x) => x.key === planKey)?.priceId?.[cycle]);
  const buyPack = (credits: number) => openCheckout(PACK_PRICE_IDS[credits]);
  const prefs = useMutation({
    mutationFn: (v: boolean) => endpoints.accountPrefs(v),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["account"] }),
    onError: (e: Error) => toast.error(e.message),
  });
  const a = acc.data;
  const n = (x: number) => x.toLocaleString(loc);

  function planFeatures(key: string, p: NonNullable<Account["plans"][string]>) {
    const out = [
      t("plan_projects_f", { n: p.projects }),
      t("plan_files_f", { n: p.files_per_project, mb: p.max_file_mb }),
      p.monthly ? t("plan_credits_month", { n: n(p.credits) }) : t("plan_credits_once", { n: n(p.credits) }),
    ];
    if (p.monthly) out.push(t("plan_rollover", { n: n(p.credits * 2) }));
    if (key !== "free") out.push(t("plan_no_training"), t("plan_max_model"));
    if (key === "ultra") out.push(t("plan_eu"), t("plan_priority"));
    return out;
  }

  return (
    <>
      <AppHeader crumb={t("usage_billing")} back />
      <main className="page-enter mx-auto w-full max-w-5xl flex-1 px-6 py-8">
        {!a ? (
          <div className="flex flex-col gap-4">{[0, 1].map((i) => <Skeleton key={i} className="h-48 rounded-2xl" />)}</div>
        ) : (
          <div className="flex flex-col gap-5">
            <Card className="p-6">
              <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
                <div>
                  <h2 className="text-sm font-bold uppercase tracking-wider text-muted-foreground">{t("credits_title")}</h2>
                  <div className="mt-1 text-3xl font-extrabold tabular-nums">{n(a.credits.remaining)}</div>
                  <div className="text-xs text-muted-foreground">{t("credits_of", { total: n(a.credits.quota + a.credits.extra) })}</div>
                </div>
                <div className="flex flex-col items-end gap-1.5">
                  <label className="flex cursor-pointer items-center gap-2 text-[13px]">
                    <input type="checkbox" checked={a.auto_recharge} disabled={prefs.isPending || (a.role !== "owner" && a.role !== "admin")}
                      onChange={(e) => prefs.mutate(e.target.checked)} className="size-4 accent-[var(--olive,#b5d33d)]" />
                    <RefreshCcw className="size-3.5 text-muted-foreground" />{t("auto_recharge")}
                  </label>
                  <span className="text-[11px] text-muted-foreground">{t("auto_recharge_hint")}</span>
                </div>
              </div>
              <div className="mb-5 h-2 overflow-hidden rounded-full bg-secondary">
                <div className="grad-olive h-full rounded-full transition-all"
                  style={{ width: `${Math.min(100, (a.credits.remaining / Math.max(1, a.credits.quota + a.credits.extra)) * 100)}%` }} />
              </div>

              <div className="grid gap-3 sm:grid-cols-3">
                {a.usage.length === 0 && <div className="text-sm text-muted-foreground sm:col-span-3">{t("usage_empty")}</div>}
                {a.usage.map((u) => (
                  <div key={u.kind} className="flex items-center gap-3 rounded-xl border border-border bg-secondary/40 px-4 py-3">
                    <span className="text-olive">{KIND_META[u.kind]?.icon}</span>
                    <span className="flex-1 text-[13px]">{t(KIND_META[u.kind]?.key ?? ("kind_chat" as Key))}<br />
                      <b className="text-muted-foreground">{u.count}×</b></span>
                    <b className="tabular-nums">{n(u.credits)}</b>
                  </div>
                ))}
              </div>

              <div className="mt-5 border-t border-border pt-4">
                <div className="mb-2 text-[12px] font-bold uppercase tracking-wider text-muted-foreground">{t("buy_credits")}</div>
                <div className="grid gap-3 sm:grid-cols-3">
                  {a.packs.map((p) => (
                    <div key={p.credits} className="flex items-center justify-between rounded-xl border border-border px-4 py-3">
                      <div>
                        <b className="tabular-nums">{n(p.credits)}</b> <span className="text-xs text-muted-foreground">{t("credits_word")}</span>
                        <div className="text-xs text-muted-foreground">€{(p.price_eur / p.credits * 1000).toFixed(1)}/1000</div>
                      </div>
                      <Button size="sm" variant="outline" disabled={a.role !== "owner" && a.role !== "admin"}
                        onClick={() => buyPack(p.credits)}>€{p.price_eur}</Button>
                    </div>
                  ))}
                </div>
                <div className="mt-2 text-[11px] text-muted-foreground">{t("packs_note")}</div>
              </div>
            </Card>

            <div>
              <div className="mb-3 flex items-center gap-4">
                <h2 className="text-sm font-bold uppercase tracking-wider text-muted-foreground">{t("plan_title")}</h2>
                <div className="inline-flex overflow-hidden rounded-lg border border-border text-[12px] font-bold">
                  {(["month", "year"] as const).map((c) => (
                    <button key={c} type="button" onClick={() => setCycle(c)} aria-pressed={cycle === c}
                      className={`px-3 py-1.5 transition-colors ${cycle === c ? "grad-olive text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`}>
                      {t(c === "month" ? "billing_monthly" : "billing_yearly")}
                    </button>
                  ))}
                </div>
                {cycle === "year" && <span className="text-[12px] font-semibold text-olive">{t("yearly_hint")}</span>}
              </div>
              <div className="grid gap-4 md:grid-cols-3">
                {Object.entries(a.plans).map(([key, p]) => {
                  const hasSub = !!sub.data?.active;
                  const current = hasSub
                    ? sub.data?.plan === key && (key === "free" || sub.data?.interval === cycle)
                    : key === a.plan;
                  const admin = a.role === "owner" || a.role === "admin";
                  const price = cycle === "month" ? p.price_eur : p.price_eur * 10;
                  return (
                    <Card key={key} className={`flex flex-col gap-3 p-5 ${current ? "border-olive/60 ring-1 ring-olive/40" : ""}`}>
                      <div className="flex items-center justify-between">
                        <h3 className="text-lg font-extrabold">{p.label}</h3>
                        {current && <span className="rounded-full bg-olive/15 px-2.5 py-0.5 text-[11px] font-extrabold text-olive">{t("current_plan")}</span>}
                      </div>
                      <div className="text-2xl font-extrabold">
                        {p.price_eur === 0 ? t("free_price") : <>€{price}<span className="text-sm font-semibold text-muted-foreground">/{t(cycle === "month" ? "per_month" : "per_year")}</span></>}
                      </div>
                      <ul className="flex flex-1 flex-col gap-1.5 text-[13px]">
                        {planFeatures(key, p).map((f) => (
                          <li key={f} className="flex items-start gap-2"><Check className="mt-0.5 size-3.5 shrink-0 text-olive" />{f}</li>
                        ))}
                      </ul>
                      {current ? (
                        <Button variant="secondary" disabled className="mt-1">{t("current_plan")}</Button>
                      ) : key === "free" ? (
                        hasSub ? (
                          <Button variant="ghost" nativeButton={false} render={<Link href="/billing" />}
                            className="mt-1 text-destructive hover:bg-destructive/10 hover:text-destructive">
                            {t("stop_subscription")}
                          </Button>
                        ) : (
                          <Button variant="secondary" disabled className="mt-1">{t("current_plan")}</Button>
                        )
                      ) : hasSub ? (
                        <Button variant="outline" disabled={!admin || change.isPending} className="mt-1"
                          onClick={async () => {
                            if (await confirm({
                              title: t("change_plan"),
                              description: t("change_plan_confirm", { name: `${p.label} · ${t(cycle === "month" ? "billing_monthly" : "billing_yearly").toLowerCase()}` }),
                              actionLabel: t("change_plan"),
                            })) change.mutate({ plan: key, interval: cycle });
                          }}>
                          {t("switch_to", { name: p.label })}
                        </Button>
                      ) : (
                        <Button disabled={!admin} className="grad-olive mt-1 font-bold text-primary-foreground hover:opacity-90"
                          onClick={() => subscribeNow(key)}>
                          {t("subscribe")}
                        </Button>
                      )}
                    </Card>
                  );
                })}
              </div>
              <div className="mt-3 text-[12px] text-muted-foreground">
                {t("projects_used_line", { used: a.projects_used, total: a.plans[a.plan]?.projects ?? 0 })}
              </div>
            </div>
          </div>
        )}
      </main>
    </>
  );
}
