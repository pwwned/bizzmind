"use client";
/* Public pricing: three tiers, monthly/yearly toggle, live localized prices
   from Paddle.PricePreview (we render only formattedTotals — no price math,
   no re-formatting), checkout as a one-page overlay. */
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useLang, useT, type Key } from "@/lib/i18n";
import { getPaddle } from "@/lib/paddle";
import { TIERS } from "@/lib/tiers";
import { Logo } from "@/components/logo";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Check } from "lucide-react";

type Cycle = "month" | "year";
interface PlanDef {
  label: string; price_eur: number; projects: number; files_per_project: number;
  max_file_mb: number; credits: number; monthly: boolean;
}

export function PricingClient({ country }: { country?: string }) {
  const t = useT();
  const { lang } = useLang();
  const [cycle, setCycle] = useState<Cycle>("month");
  const [totals, setTotals] = useState<Record<string, string>>({});   // priceId -> formatted total
  const [error, setError] = useState("");
  const [email, setEmail] = useState<string | null>(null);
  const [orgId, setOrgId] = useState<string | null>(null);

  const plans = useQuery({
    queryKey: ["public-plans"],
    queryFn: () => api<{ plans: Record<string, PlanDef> }>("/api/plans"),
    staleTime: 10 * 60_000,
  });

  useEffect(() => {   // prefill checkout email when signed in; anonymous must NOT trigger the 401 redirect
    fetch("/api/auth/me", { credentials: "same-origin" })
      .then((r) => (r.ok ? r.json() : null))
      .then((m: { email?: string; orgs?: string[] } | null) => {
        if (m?.email) setEmail(m.email);
        if (m?.orgs?.length) setOrgId(m.orgs[0]);
      })
      .catch(() => {});
  }, []);

  const priceIds = useMemo(
    () => TIERS.flatMap((tier) => (tier.priceId ? [tier.priceId.month, tier.priceId.year] : [])).filter(Boolean),
    [],
  );

  useEffect(() => {
    if (!priceIds.length) { setError(t("pricing_not_configured")); return; }
    let dead = false;
    (async () => {
      try {
        const paddle = await getPaddle();
        if (!paddle) throw new Error("Paddle.js failed to load");
        const res = await paddle.PricePreview({
          items: priceIds.map((priceId) => ({ priceId, quantity: 1 })),
          ...(country ? { address: { countryCode: country } } : {}),
        });
        if (dead) return;
        const out: Record<string, string> = {};
        for (const li of res.data.details.lineItems) out[li.price.id] = li.formattedTotals.total;
        setTotals(out);
      } catch (e) { if (!dead) setError((e as Error).message); }
    })();
    return () => { dead = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [country, priceIds.join("|")]);

  async function subscribe(priceId: string) {
    try {
      const paddle = await getPaddle();
      if (!paddle) throw new Error("Paddle.js failed to load");
      paddle.Checkout.open({
        items: [{ priceId, quantity: 1 }],
        ...(email ? { customer: { email } } : {}),
        ...(orgId ? { customData: { org_id: orgId } } : {}),
        settings: {
          displayMode: "overlay",
          variant: "one-page",
          successUrl: `${window.location.origin}/welcome`,
          locale: lang,
        },
      });
    } catch (e) { setError((e as Error).message); }
  }

  function features(key: string, p: PlanDef) {
    const out = [
      t("plan_projects_f", { n: p.projects }),
      t("plan_files_f", { n: p.files_per_project, mb: p.max_file_mb }),
      p.monthly ? t("plan_credits_month", { n: p.credits.toLocaleString() }) : t("plan_credits_once", { n: p.credits.toLocaleString() }),
    ];
    if (p.monthly) out.push(t("plan_rollover", { n: (p.credits * 2).toLocaleString() }));
    if (key !== "free") out.push(t("plan_no_training"), t("plan_max_model"));
    if (key === "ultra") out.push(t("plan_eu"), t("plan_priority"));
    return out;
  }

  return (
    <main className="page-enter mx-auto flex w-full max-w-5xl flex-col items-center px-6 py-12">
      <Link href="/" className="mb-8"><Logo size={32} /></Link>
      <h1 className="text-3xl font-extrabold">{t("pricing_title")}</h1>
      <p className="mt-2 text-sm text-muted-foreground">{t("pricing_sub")}</p>

      <div className="mt-6 inline-flex overflow-hidden rounded-xl border border-border text-[13px] font-bold">
        {(["month", "year"] as Cycle[]).map((c) => (
          <button key={c} type="button" onClick={() => setCycle(c)} aria-pressed={cycle === c}
            className={`px-4 py-2 transition-colors ${cycle === c ? "grad-olive text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`}>
            {t(c === "month" ? "billing_monthly" : "billing_yearly")}
          </button>
        ))}
      </div>
      {cycle === "year" && <div className="mt-2 text-[12px] font-semibold text-olive">{t("yearly_hint")}</div>}

      {error && <div className="mt-6 max-w-lg rounded-xl border border-yellow-600/40 bg-yellow-500/10 p-3 text-center text-[13px] text-yellow-600 dark:text-yellow-400">{error}</div>}

      <div className="mt-8 grid w-full gap-4 md:grid-cols-3">
        {TIERS.map((tier) => {
          const p = plans.data?.plans?.[tier.key];
          if (!p) return <Card key={tier.key} className="h-80 animate-pulse" />;
          const pid = tier.priceId?.[cycle];
          const total = pid ? totals[pid] : undefined;
          const highlight = tier.key === "pro";
          return (
            <Card key={tier.key} className={`flex flex-col gap-3 p-6 ${highlight ? "border-olive/60 ring-1 ring-olive/40" : ""}`}>
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-extrabold">{p.label}</h2>
                {highlight && <span className="rounded-full bg-olive/15 px-2.5 py-0.5 text-[11px] font-extrabold text-olive">{t("most_popular")}</span>}
              </div>
              <div className="min-h-10 text-3xl font-extrabold tabular-nums">
                {tier.priceId === null ? t("free_price") : total ?? <span className="text-base text-muted-foreground">…</span>}
                {tier.priceId !== null && total && (
                  <span className="text-sm font-semibold text-muted-foreground">/{t(cycle === "month" ? "per_month" : "per_year")}</span>
                )}
              </div>
              <ul className="flex flex-1 flex-col gap-1.5 text-[13px]">
                {features(tier.key, p).map((f) => (
                  <li key={f} className="flex items-start gap-2"><Check className="mt-0.5 size-3.5 shrink-0 text-olive" />{f}</li>
                ))}
              </ul>
              {tier.priceId === null ? (
                <Button variant="outline" nativeButton={false} render={<Link href="/login" />}>{t("start_free")}</Button>
              ) : (
                <Button disabled={!pid || !total} onClick={() => pid && subscribe(pid)}
                  className={highlight ? "grad-olive font-bold text-primary-foreground hover:opacity-90" : ""}
                  variant={highlight ? "default" : "outline"}>
                  {t("subscribe")}
                </Button>
              )}
            </Card>
          );
        })}
      </div>
    </main>
  );
}
