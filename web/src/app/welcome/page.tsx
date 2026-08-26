"use client";
import Link from "next/link";
import { useT } from "@/lib/i18n";
import { Logo } from "@/components/logo";
import { Button } from "@/components/ui/button";
import { PartyPopper } from "lucide-react";

export default function WelcomePage() {
  const t = useT();
  return (
    <main className="page-enter flex min-h-screen flex-col items-center justify-center gap-5 px-6 text-center">
      <Logo size={36} />
      <PartyPopper className="size-10 text-olive" />
      <h1 className="text-2xl font-extrabold">{t("welcome_title")}</h1>
      <p className="max-w-md text-sm leading-relaxed text-muted-foreground">{t("welcome_text")}</p>
      <Button nativeButton={false} render={<Link href="/app" />} className="grad-olive font-bold text-primary-foreground hover:opacity-90">
        {t("welcome_cta")}
      </Button>
    </main>
  );
}
