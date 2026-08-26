"use client";
/* Account: profile & settings — who you are, password change. */
import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { endpoints } from "@/lib/api";
import { useT, type Key } from "@/lib/i18n";
import { AppHeader } from "@/components/app-header";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { KeyRound } from "lucide-react";

export default function AccountPage() {
  const t = useT();
  const acc = useQuery({ queryKey: ["account"], queryFn: endpoints.account });
  const [pw1, setPw1] = useState("");
  const [pw2, setPw2] = useState("");
  const changePw = useMutation({
    mutationFn: (p: string) => endpoints.changePassword(p),
    onSuccess: () => { setPw1(""); setPw2(""); toast.success(t("password_changed")); },
    onError: (e: Error) => toast.error(e.message),
  });
  const a = acc.data;

  return (
    <>
      <AppHeader crumb={t("account_settings")} back />
      <main className="page-enter mx-auto w-full max-w-2xl flex-1 px-6 py-8">
        {!a ? <Skeleton className="h-52 rounded-2xl" /> : (
          <Card className="p-6">
            <div className="mb-6 flex items-center gap-3">
              <span className="inline-flex size-12 items-center justify-center rounded-full border border-olive/40 bg-olive/10 text-lg font-extrabold text-olive">{a.email[0]?.toUpperCase()}</span>
              <div>
                <div className="text-lg font-bold">{a.email}</div>
                <div className="text-sm text-muted-foreground">{a.org_name} · {t("role_" + (a.role === "owner" || a.role === "admin" ? a.role : "member") as Key)}</div>
              </div>
            </div>
            <h2 className="mb-3 text-[12px] font-bold uppercase tracking-wider text-muted-foreground">{t("change_password")}</h2>
            <form
              className="flex flex-wrap items-center gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                if (pw1 !== pw2) { toast.error(t("password_mismatch")); return; }
                changePw.mutate(pw1);
              }}
            >
              <KeyRound className="size-4 text-muted-foreground" />
              <Input type="password" autoComplete="new-password" placeholder={t("new_password")} value={pw1} onChange={(e) => setPw1(e.target.value)} className="w-52" />
              <Input type="password" autoComplete="new-password" placeholder={t("repeat_password")} value={pw2} onChange={(e) => setPw2(e.target.value)} className="w-52" />
              <Button type="submit" variant="outline" disabled={changePw.isPending || pw1.length < 8 || pw2.length < 8}>
                {t("change_password")}
              </Button>
            </form>
          </Card>
        )}
      </main>
    </>
  );
}
