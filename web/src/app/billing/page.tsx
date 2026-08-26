"use client";
/* Billing, fully in-app: live subscription state, card change as an overlay
   on our own page, cancel/keep with our dialogs, invoices downloaded through
   our domain. No external billing site anywhere. */
import { useEffect, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, endpoints } from "@/lib/api";
import { localeOf, useLang, useT, type Key } from "@/lib/i18n";
import { getPaddle } from "@/lib/paddle";
import { useConfirm } from "@/components/confirm-dialog";
import { AppHeader } from "@/components/app-header";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ArrowUpDown, CreditCard, Download, FileText, Undo2 } from "lucide-react";

type Billing = {
  company: string; eik: string; vat_id: string; mol: string;
  address: string; city: string; country: string; invoice_email: string;
};
const EMPTY: Billing = { company: "", eik: "", vat_id: "", mol: "", address: "", city: "", country: "", invoice_email: "" };
const FIELDS: { k: keyof Billing; key: Key; wide?: boolean }[] = [
  { k: "company", key: "company", wide: true },
  { k: "eik", key: "eik" },
  { k: "vat_id", key: "vat_id" },
  { k: "mol", key: "mol" },
  { k: "invoice_email", key: "invoice_email" },
  { k: "address", key: "address", wide: true },
  { k: "city", key: "city" },
  { k: "country", key: "country" },
];

const money = (cents?: string, cur?: string) =>
  cents ? `${(parseInt(cents, 10) / 100).toFixed(2)} ${cur ?? ""}` : "";

export default function BillingPage() {
  const t = useT();
  const { lang } = useLang();
  const loc = localeOf(lang);
  const qc = useQueryClient();
  const confirm = useConfirm();
  const acc = useQuery({ queryKey: ["account"], queryFn: endpoints.account });
  const sub = useQuery({ queryKey: ["subscription"], queryFn: endpoints.subscription });
  const invoices = useQuery({ queryKey: ["invoices"], queryFn: endpoints.invoices });
  const cards = useQuery({ queryKey: ["payment-methods"], queryFn: endpoints.paymentMethods });
  const removeCard = useMutation({
    mutationFn: (id: string) => endpoints.removePaymentMethod(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["payment-methods"] }); toast.success(t("card_removed")); },
    onError: (e: Error) => toast.error(e.message),
  });
  const [form, setForm] = useState<Billing>(EMPTY);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [reasonText, setReasonText] = useState("");
  useEffect(() => {
    if (acc.data) setForm({ ...EMPTY, ...(acc.data.billing ?? {}) });
  }, [acc.data]);

  const save = useMutation({
    mutationFn: (b: Billing) => api<{ ok: boolean }>("/api/account/billing", { method: "POST", body: JSON.stringify(b) }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["account"] }); toast.success(t("billing_saved")); },
    onError: (e: Error) => toast.error(e.message),
  });
  const cancel = useMutation({
    mutationFn: () => endpoints.subCancel(reason, reasonText.trim()),
    onSuccess: () => { setCancelOpen(false); qc.invalidateQueries({ queryKey: ["subscription"] }); toast.success(t("sub_cancel_done")); },
    onError: (e: Error) => toast.error(e.message),
  });
  const change = useMutation({
    mutationFn: (v: { plan: string; interval: string }) => endpoints.subChange(v.plan, v.interval),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["subscription"] });
      qc.invalidateQueries({ queryKey: ["account"] });
      toast.success(t("plan_changed"));
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const keep = useMutation({
    mutationFn: endpoints.subKeep,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["subscription"] }); toast.success(t("sub_kept")); },
    onError: (e: Error) => toast.error(e.message),
  });

  async function changeCard() {
    try {
      const { transaction_id } = await endpoints.paymentMethodTxn();
      const paddle = await getPaddle();
      if (!paddle) throw new Error("payment overlay failed to load");
      paddle.Checkout.open({
        transactionId: transaction_id,
        settings: { displayMode: "overlay", variant: "one-page", locale: lang },
      });
    } catch (e) { toast.error((e as Error).message); }
  }

  const a = acc.data;
  const s = sub.data;
  const admin = a && (a.role === "owner" || a.role === "admin");
  const dateFmt = (iso?: string | null) => (iso ? new Date(iso).toLocaleDateString(loc) : "");

  return (
    <>
      <AppHeader crumb={t("billing_title")} back />
      <main className="page-enter mx-auto w-full max-w-2xl flex-1 px-6 py-8">
        {!a || !s ? <Skeleton className="h-72 rounded-2xl" /> : (
          <div className="flex flex-col gap-5">
            {/* subscription */}
            <Card className="p-6">
              <div className="mb-1 flex items-center gap-2">
                <CreditCard className="size-4 text-olive" />
                <h2 className="text-[12px] font-bold uppercase tracking-wider text-muted-foreground">{t("subscription_title")}</h2>
              </div>
              <div className="mb-4 text-[11.5px] text-muted-foreground">{t("paddle_note")}</div>
              {s.active ? (
                <div className="flex flex-col gap-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-lg font-extrabold">{a.plans[s.plan ?? ""]?.label ?? s.plan}</span>
                        <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-extrabold ${s.status === "past_due" ? "bg-destructive/15 text-destructive" : "bg-olive/15 text-olive"}`}>
                          {t(("sub_status_" + s.status) as Key)}
                        </span>
                      </div>
                      <div className="mt-1 text-sm text-muted-foreground">
                        {s.cancel_scheduled_at
                          ? t("sub_ends_line", { date: dateFmt(s.cancel_scheduled_at) })
                          : t("sub_next_line", { amount: money(s.amount, s.currency), date: dateFmt(s.next_billed_at) })}
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {s.interval === "month" && !s.cancel_scheduled_at && (
                        <Button className="grad-olive font-bold text-primary-foreground hover:opacity-90"
                          disabled={!admin} onClick={async () => {
                            if (await confirm({ title: t("switch_annual"), description: t("switch_annual_desc"), actionLabel: t("switch_annual") }))
                              endpoints.subChange(s.plan ?? "pro", "year").then(() => {
                                qc.invalidateQueries({ queryKey: ["subscription"] });
                                toast.success(t("plan_changed"));
                              }).catch((e: Error) => toast.error(e.message));
                          }}>
                          {t("switch_annual_save")}
                        </Button>
                      )}
                      <Button variant="outline" disabled={!admin} onClick={changeCard}>
                        <CreditCard className="size-4" />{t("change_card")}
                      </Button>
                      {s.cancel_scheduled_at ? (
                        <Button variant="outline" disabled={!admin || keep.isPending} onClick={() => keep.mutate()}>
                          <Undo2 className="size-4" />{t("keep_subscription")}
                        </Button>
                      ) : (
                        <Button variant="ghost" className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                          disabled={!admin || cancel.isPending}
                          onClick={() => { setReason(""); setReasonText(""); setCancelOpen(true); }}>
                          {t("cancel_subscription")}
                        </Button>
                      )}
                    </div>
                  </div>

                  <div className="border-t border-border pt-4">
                    <div className="mb-2 flex items-center gap-2 text-[12px] font-bold uppercase tracking-wider text-muted-foreground">
                      <ArrowUpDown className="size-3.5" />{t("change_plan")}
                    </div>
                    <div className="grid gap-2 sm:grid-cols-2">
                      {(["pro", "ultra"] as const).flatMap((pk) =>
                        (["month", "year"] as const).map((iv) => {
                          const def = a.plans[pk];
                          if (!def) return null;
                          const price = iv === "month" ? def.price_eur : def.price_eur * 10;
                          const current = s.plan === pk && s.interval === iv;
                          return (
                            <button key={pk + iv} type="button" disabled={!admin || current || change.isPending}
                              onClick={async () => {
                                if (await confirm({
                                  title: t("change_plan"),
                                  description: t("change_plan_confirm", { name: `${def.label} · ${t(iv === "month" ? "billing_monthly" : "billing_yearly").toLowerCase()}` }),
                                  actionLabel: t("change_plan"),
                                })) change.mutate({ plan: pk, interval: iv });
                              }}
                              className={`flex items-center justify-between rounded-xl border px-4 py-2.5 text-left text-[13px] transition-colors ${current ? "border-olive bg-olive/10" : "border-border bg-secondary/40 hover:border-olive/50"} ${!admin || current ? "cursor-default" : ""}`}>
                              <span><b>{def.label}</b> · {t(iv === "month" ? "billing_monthly" : "billing_yearly").toLowerCase()}</span>
                              <span className="tabular-nums">
                                €{price}<span className="text-[11px] text-muted-foreground">/{t(iv === "month" ? "per_month" : "per_year")}</span>
                                {current && <span className="ml-2 rounded-full bg-olive/20 px-2 py-0.5 text-[10px] font-extrabold text-olive">{t("current_plan")}</span>}
                              </span>
                            </button>
                          );
                        }),
                      )}
                    </div>
                    <div className="mt-1.5 text-[11px] text-muted-foreground">{t("proration_note")}</div>
                  </div>

                  {(invoices.data?.invoices?.length ?? 0) > 0 && (
                    <div className="border-t border-border pt-4">
                      <div className="mb-2 text-[12px] font-bold uppercase tracking-wider text-muted-foreground">{t("invoices_title")}</div>
                      <ul className="flex flex-col gap-1.5">
                        {invoices.data!.invoices.map((inv) => (
                          <li key={inv.id} className="flex items-center gap-3 rounded-lg border border-border bg-secondary/40 px-3 py-2 text-[13px]">
                            <span className="tabular-nums text-muted-foreground">{inv.date}</span>
                            <span className="flex-1 truncate">{inv.number ?? inv.id.slice(-8)}</span>
                            <b className="tabular-nums">{money(inv.total, inv.currency)}</b>
                            <a href={`/api/account/invoice/${encodeURIComponent(inv.id)}`}
                              className="rounded p-1 text-muted-foreground hover:text-olive" title={t("download_invoice")}>
                              <Download className="size-4" />
                            </a>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              ) : (
                <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-border p-5 text-center text-sm text-muted-foreground">
                  {t("no_subscription")}
                  <Button variant="outline" nativeButton={false} render={<Link href="/pricing" />}>{t("see_pricing")}</Button>
                </div>
              )}
              {(cards.data?.cards?.length ?? 0) > 0 && (
                <div className="mt-4 border-t border-border pt-4">
                  <div className="mb-2 text-[12px] font-bold uppercase tracking-wider text-muted-foreground">{t("saved_cards")}</div>
                  <ul className="flex flex-col gap-1.5">
                    {cards.data!.cards.map((c) => (
                      <li key={c.id} className="flex items-center gap-3 rounded-lg border border-border bg-secondary/40 px-3 py-2 text-[13px]">
                        <CreditCard className="size-4 text-olive" />
                        <span className="flex-1">{c.type} •••• {c.last4}</span>
                        <Button size="sm" variant="ghost" className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                          disabled={!admin || removeCard.isPending}
                          onClick={async () => {
                            if (await confirm({ title: t("remove_card"), description: t("remove_card_confirm"), actionLabel: t("remove_card"), destructive: true }))
                              removeCard.mutate(c.id);
                          }}>
                          {t("remove_card")}
                        </Button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </Card>

            {/* invoice details */}
            <Card className="p-6">
              <div className="mb-4 flex items-center gap-2">
                <FileText className="size-4 text-olive" />
                <h2 className="text-[12px] font-bold uppercase tracking-wider text-muted-foreground">{t("invoice_details")}</h2>
              </div>
              <form className="grid grid-cols-2 gap-3" onSubmit={(e) => { e.preventDefault(); save.mutate(form); }}>
                {FIELDS.map((f) => (
                  <label key={f.k} className={`flex flex-col gap-1 text-[11px] font-semibold text-muted-foreground ${f.wide ? "col-span-2" : ""}`}>
                    {t(f.key)}
                    <Input value={form[f.k]} disabled={!admin} onChange={(e) => setForm({ ...form, [f.k]: e.target.value })} className="text-[13px]" />
                  </label>
                ))}
                <div className="col-span-2 mt-1 flex justify-end">
                  <Button type="submit" disabled={!admin || save.isPending} className="grad-olive font-bold text-primary-foreground hover:opacity-90">
                    {t("save")}
                  </Button>
                </div>
              </form>
            </Card>
          </div>
        )}
      </main>

      <Dialog open={cancelOpen} onOpenChange={setCancelOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t("cancel_subscription")}</DialogTitle>
            <DialogDescription>{t("cancel_sub_confirm")}</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-2">
            <div className="text-[12px] font-bold uppercase tracking-wider text-muted-foreground">{t("cancel_reason_title")}</div>
            {(["expensive", "unused", "missing_features", "technical", "switching", "other"] as const).map((r) => (
              <label key={r} className="flex cursor-pointer items-center gap-2.5 rounded-lg border border-border px-3 py-2 text-[13px] has-[:checked]:border-olive has-[:checked]:bg-olive/10">
                <input type="radio" name="cancel-reason" checked={reason === r} onChange={() => setReason(r)}
                  className="size-3.5 accent-[var(--olive,#b5d33d)]" />
                {t(("reason_" + r) as Key)}
              </label>
            ))}
            <Textarea value={reasonText} onChange={(e) => setReasonText(e.target.value)} placeholder={t("cancel_comment_ph")} rows={2} className="mt-1 text-[13px]" />
          </div>
          <DialogFooter className="gap-2">
            <Button variant="ghost" onClick={() => setCancelOpen(false)}>{t("cancel")}</Button>
            <Button className="bg-destructive text-white hover:bg-destructive/90" disabled={!reason || cancel.isPending} onClick={() => cancel.mutate()}>
              {t("cancel_subscription")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
