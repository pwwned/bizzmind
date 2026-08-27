"use client";
/* Always-visible credits chip in the app header (the Gamma pattern):
   balance at a glance; the popover holds refresh date, rollover note,
   one-click buy and auto-recharge. */
import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, cacheGet, cacheSet, endpoints, useCachedPlaceholder, type Account } from "@/lib/api";
import { localeOf, useLang, useT } from "@/lib/i18n";
import { getPaddle } from "@/lib/paddle";
import { PACK_PRICE_IDS } from "@/lib/tiers";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuGroup, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { RefreshCcw, Sparkles } from "lucide-react";

export function CreditsChip() {
  const t = useT();
  const { lang } = useLang();
  const loc = localeOf(lang);
  const qc = useQueryClient();
  const hydrated = useCachedPlaceholder();
  const acc = useQuery({
    queryKey: ["account"],
    queryFn: async () => { const d = await endpoints.account(); cacheSet("account", d); return d; },
    placeholderData: () => (hydrated ? cacheGet<Account>("account") : undefined),
    staleTime: 60_000,
  });
  const sub = useQuery({ queryKey: ["subscription"], queryFn: endpoints.subscription, staleTime: 60_000 });
  const [buyOpen, setBuyOpen] = useState(false);
  const [pack, setPack] = useState(4000);
  const [buying, setBuying] = useState(false);

  const prefs = useMutation({
    mutationFn: (v: boolean) => endpoints.accountPrefs(v),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["account"] }),
    onError: (e: Error) => toast.error(e.message),
  });

  const a = acc.data;
  if (!a) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-[12px] font-extrabold text-muted-foreground">
        <Sparkles className="size-3.5 opacity-50" />
        <span className="inline-block h-3 w-8 animate-pulse rounded bg-muted" />
      </span>
    );
  }
  const n = (x: number) => x.toLocaleString(loc);
  const admin = a.role === "owner" || a.role === "admin";
  const plan = a.plans[a.plan];
  const refreshDate = sub.data?.active && sub.data.next_billed_at
    ? new Date(sub.data.next_billed_at).toLocaleDateString(loc) : null;
  const packDef = a.packs.find((p) => p.credits === pack) ?? a.packs[1];

  async function buy() {
    if (!a) return;
    setBuying(true);
    try {
      const r = await api<{ status: string }>("/api/account/buy-credits", {
        method: "POST", body: JSON.stringify({ credits: pack }),
      });
      if (r.status === "charged") {
        toast.success(t("credits_added", { n: n(pack) }));
        setBuyOpen(false);
        qc.invalidateQueries({ queryKey: ["account"] });
        qc.invalidateQueries({ queryKey: ["pres-credits"] });
      } else if (r.status === "pending") {
        toast.success(t("credits_pending"));
        setBuyOpen(false);
      } else {
        // no saved card — normal checkout overlay
        const paddle = await getPaddle();
        const priceId = PACK_PRICE_IDS[pack];
        if (!paddle || !priceId) throw new Error(t("pricing_not_configured"));
        setBuyOpen(false);
        paddle.Checkout.open({
          items: [{ priceId, quantity: 1 }],
          ...(a.email ? { customer: { email: a.email } } : {}),
          ...(a.org_id ? { customData: { org_id: a.org_id } } : {}),
          settings: { displayMode: "overlay", variant: "one-page", locale: lang },
        });
      }
    } catch (e) { toast.error((e as Error).message); }
    finally { setBuying(false); }
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger
          className="inline-flex items-center gap-1.5 rounded-full border border-olive/40 bg-olive/10 px-3 py-1.5 text-[12px] font-extrabold tabular-nums text-olive transition-colors hover:bg-olive/20"
          title={t("credits_title")}
        >
          <Sparkles className="size-3.5" />{n(a.credits.remaining)}
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-72 p-4">
          <DropdownMenuGroup>
            <div className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">{t("your_credits")}</div>
            <div className="mt-1 text-2xl font-extrabold tabular-nums">{n(a.credits.remaining)}</div>
            <div className="mt-2 flex flex-col gap-1 text-[12px] text-muted-foreground">
              {refreshDate && plan?.monthly && <div>{t("credits_refresh_on", { date: refreshDate })}</div>}
              {plan?.monthly && <div>{t("plan_rollover", { n: n(plan.credits * 2) })}</div>}
            </div>
            <div className="mt-3 flex gap-2">
              <Button size="sm" className="grad-olive flex-1 font-bold text-primary-foreground hover:opacity-90"
                disabled={!admin} onClick={() => setBuyOpen(true)}>
                {t("buy_credits")}
              </Button>
            </div>
            <label className="mt-2.5 flex cursor-pointer items-center gap-2 text-[12px]">
              <input type="checkbox" checked={a.auto_recharge} disabled={prefs.isPending || !admin}
                onChange={(e) => prefs.mutate(e.target.checked)} className="size-3.5 accent-[var(--olive,#b5d33d)]" />
              <RefreshCcw className="size-3 text-muted-foreground" />{t("auto_recharge")}
            </label>
            <div className="mt-3 border-t border-border pt-2.5 text-[11.5px] leading-relaxed text-muted-foreground">
              <b>{t("faq_what_uses")}</b> {t("faq_what_uses_a")}<br />
              <b>{t("faq_how_many")}</b> {t("faq_how_many_a", { n: n(plan?.credits ?? 0) })}
            </div>
            <Link href="/pricing" className="mt-2 inline-block text-[12px] font-semibold text-olive hover:underline">
              {t("usage_billing")} →
            </Link>
          </DropdownMenuGroup>
        </DropdownMenuContent>
      </DropdownMenu>

      <Dialog open={buyOpen} onOpenChange={(v) => { if (!buying) setBuyOpen(v); }}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader><DialogTitle>{t("buy_credits")}</DialogTitle></DialogHeader>
          <div className="flex flex-col gap-3">
            <label className="flex flex-col gap-1 text-[12px] font-semibold text-muted-foreground">
              {t("how_many_credits")}
              <select value={pack} onChange={(e) => setPack(parseInt(e.target.value, 10))}
                className="h-10 rounded-lg border border-border bg-secondary/40 px-3 text-sm font-bold text-foreground outline-none focus:border-olive">
                {a.packs.map((p) => (
                  <option key={p.credits} value={p.credits}>{n(p.credits)} {t("credits_word")}</option>
                ))}
              </select>
            </label>
            <div className="flex items-center justify-between rounded-xl border border-border bg-secondary/40 px-4 py-3">
              <span className="text-[13px]">{t("due_today")}</span>
              <b className="text-lg tabular-nums">€{packDef?.price_eur}</b>
            </div>
            <div className="text-[11.5px] text-muted-foreground">{t("charge_saved_method")}</div>
          </div>
          <DialogFooter>
            <Button variant="ghost" disabled={buying} onClick={() => setBuyOpen(false)}>{t("cancel")}</Button>
            <Button className="grad-olive font-bold text-primary-foreground hover:opacity-90" disabled={buying} onClick={buy}>
              {buying ? t("generating") : t("buy_credits")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
