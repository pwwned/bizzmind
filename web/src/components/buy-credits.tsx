"use client";
/* Buying credits never takes you off the page you were working on: the dialog
   opens in place, the payment is an overlay, and you stay exactly where you
   were with a refreshed balance. */
import { createContext, useContext, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, endpoints, type Account } from "@/lib/api";
import { localeOf, useLang, useT } from "@/lib/i18n";
import { getPaddle } from "@/lib/paddle";
import { PACK_PRICE_IDS } from "@/lib/tiers";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";

const BuyContext = createContext<(needed?: number) => void>(() => {});

/** Open the buy-credits dialog from anywhere. */
export function useBuyCredits() {
  return useContext(BuyContext);
}

export function BuyCreditsProvider({ children }: { children: React.ReactNode }) {
  const t = useT();
  const { lang } = useLang();
  const loc = localeOf(lang);
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [needed, setNeeded] = useState<number | undefined>();
  const [pack, setPack] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  const acc = useQuery({ queryKey: ["account"], queryFn: endpoints.account, enabled: open });
  const a = acc.data;
  const n = (x: number) => x.toLocaleString(loc);

  function openDialog(need?: number) {
    setNeeded(need);
    setPack(null);
    setOpen(true);
  }

  function refreshBalances() {
    qc.invalidateQueries({ queryKey: ["account"] });
    qc.invalidateQueries({ queryKey: ["pres-credits"] });
    qc.invalidateQueries({ queryKey: ["quote"] });
  }

  // the smallest pack that covers the shortfall is pre-selected
  const packs = a?.packs ?? [];
  const shortfall = needed && a ? Math.max(0, needed - a.credits.remaining) : 0;
  const suggested = packs.find((p) => p.credits >= shortfall) ?? packs[packs.length - 1];
  const chosen = pack ?? suggested?.credits ?? 0;
  const chosenPack = packs.find((p) => p.credits === chosen);

  async function buy() {
    if (!a || !chosen) return;
    setBusy(true);
    try {
      const r = await api<{ status: string }>("/api/account/buy-credits", {
        method: "POST", body: JSON.stringify({ credits: chosen }),
      });
      if (r.status === "charged" || r.status === "pending") {
        toast.success(r.status === "charged" ? t("credits_added", { n: n(chosen) }) : t("credits_pending"));
        setOpen(false);
        refreshBalances();
        return;
      }
      const paddle = await getPaddle();                 // no saved card → overlay, still in place
      const priceId = PACK_PRICE_IDS[chosen];
      if (!paddle || !priceId) throw new Error(t("pricing_not_configured"));
      setOpen(false);
      paddle.Checkout.open({
        items: [{ priceId, quantity: 1 }],
        ...(a.email ? { customer: { email: a.email } } : {}),
        ...(a.org_id ? { customData: { org_id: a.org_id } } : {}),
        settings: { displayMode: "overlay", variant: "one-page", locale: lang },
        // no successUrl on purpose: Paddle closes the overlay and the user
        // stays on the page they were working on
      });
      // credits land through the webhook; poll briefly so the balance catches up
      let tries = 0;
      const tick = setInterval(() => {
        tries += 1;
        refreshBalances();
        if (tries > 12) clearInterval(tick);
      }, 5000);
    } catch (e) { toast.error((e as Error).message); }
    finally { setBusy(false); }
  }

  return (
    <BuyContext.Provider value={openDialog}>
      {children}
      <Dialog open={open} onOpenChange={(v) => { if (!busy) setOpen(v); }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t("buy_credits")}</DialogTitle>
            {a && (
              <DialogDescription>
                {needed
                  ? t("buy_needed", { need: n(needed), left: n(a.credits.remaining) })
                  : t("buy_have", { left: n(a.credits.remaining) })}
              </DialogDescription>
            )}
          </DialogHeader>
          <div className="flex flex-col gap-2">
            {packs.map((p) => {
              const on = p.credits === chosen;
              const covers = !needed || p.credits >= shortfall;
              return (
                <button key={p.credits} type="button" onClick={() => setPack(p.credits)}
                  className={`flex items-center justify-between rounded-xl border px-4 py-3 text-left transition-colors ${on ? "border-olive bg-olive/10" : "border-border hover:border-olive/50"}`}>
                  <span>
                    <b className="tabular-nums">{n(p.credits)}</b>{" "}
                    <span className="text-[12px] text-muted-foreground">{t("credits_word")}</span>
                    <span className="block text-[11px] text-muted-foreground">
                      €{(p.price_eur / p.credits * 1000).toFixed(1)}/1000
                      {needed && covers ? ` · ${t("covers_action")}` : ""}
                    </span>
                  </span>
                  <b className="text-lg tabular-nums">€{p.price_eur}</b>
                </button>
              );
            })}
            <div className="text-[11.5px] text-muted-foreground">{t("charge_saved_method")}</div>
          </div>
          <DialogFooter>
            <Button variant="ghost" disabled={busy} onClick={() => setOpen(false)}>{t("cancel")}</Button>
            <Button className="grad-olive font-bold text-primary-foreground hover:opacity-90"
              disabled={busy || !chosenPack} onClick={buy}>
              {busy ? t("generating") : chosenPack ? t("buy_for", { price: chosenPack.price_eur }) : t("buy_credits")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </BuyContext.Provider>
  );
}
