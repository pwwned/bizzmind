"use client";
/* Billing: invoice details (stored on the organisation) + payment method
   placeholder until the payment provider is connected. */
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, endpoints } from "@/lib/api";
import { useT, type Key } from "@/lib/i18n";
import { AppHeader } from "@/components/app-header";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { CreditCard, FileText } from "lucide-react";

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

export default function BillingPage() {
  const t = useT();
  const qc = useQueryClient();
  const acc = useQuery({ queryKey: ["account"], queryFn: endpoints.account });
  const [form, setForm] = useState<Billing>(EMPTY);
  useEffect(() => {
    if (acc.data) setForm({ ...EMPTY, ...(acc.data.billing ?? {}) });
  }, [acc.data]);
  const save = useMutation({
    mutationFn: (b: Billing) => api<{ ok: boolean }>("/api/account/billing", { method: "POST", body: JSON.stringify(b) }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["account"] }); toast.success(t("billing_saved")); },
    onError: (e: Error) => toast.error(e.message),
  });
  const a = acc.data;
  const admin = a && (a.role === "owner" || a.role === "admin");

  return (
    <>
      <AppHeader crumb={t("billing_title")} back />
      <main className="page-enter mx-auto w-full max-w-2xl flex-1 px-6 py-8">
        {!a ? <Skeleton className="h-72 rounded-2xl" /> : (
          <div className="flex flex-col gap-5">
            <Card className="p-6">
              <div className="mb-4 flex items-center gap-2">
                <CreditCard className="size-4 text-olive" />
                <h2 className="text-[12px] font-bold uppercase tracking-wider text-muted-foreground">{t("payment_method")}</h2>
              </div>
              <div className="rounded-xl border border-dashed border-border p-5 text-center text-sm text-muted-foreground">
                {t("payment_box")}
              </div>
            </Card>

            <Card className="p-6">
              <div className="mb-4 flex items-center gap-2">
                <FileText className="size-4 text-olive" />
                <h2 className="text-[12px] font-bold uppercase tracking-wider text-muted-foreground">{t("invoice_details")}</h2>
              </div>
              <form
                className="grid grid-cols-2 gap-3"
                onSubmit={(e) => { e.preventDefault(); save.mutate(form); }}
              >
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
    </>
  );
}
