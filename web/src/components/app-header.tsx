"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { endpoints } from "@/lib/api";
import { useLang, useT } from "@/lib/i18n";
import { Logo } from "@/components/logo";
import { Button } from "@/components/ui/button";
import { ArrowLeft, LogOut } from "lucide-react";

export function AppHeader({ crumb, back }: { crumb?: string; back?: boolean }) {
  const t = useT();
  const { lang, setLang } = useLang();
  const router = useRouter();
  const me = useQuery({ queryKey: ["me"], queryFn: endpoints.me, staleTime: 5 * 60_000 });

  return (
    <header className="sticky top-0 z-40 flex items-center gap-4 border-b border-border bg-background/70 px-6 py-3 backdrop-blur-md">
      <Link href="/app" className="shrink-0"><Logo size={28} /></Link>
      {crumb && (
        <span className="truncate text-sm text-muted-foreground">
          / <b className="font-semibold text-foreground">{crumb}</b>
        </span>
      )}
      <span className="flex-1" />
      {back && (
        <Button variant="outline" size="sm" nativeButton={false} render={<Link href="/app" />}>
          <ArrowLeft className="size-4" />{t("all_projects")}
        </Button>
      )}
      <div className="inline-flex overflow-hidden rounded-lg border border-border text-[11px] font-extrabold tracking-wide">
        {(["bg", "en"] as const).map((l) => (
          <button
            key={l}
            type="button"
            onClick={() => setLang(l)}
            aria-pressed={lang === l}
            className={`px-2.5 py-1.5 transition-colors ${lang === l ? "grad-olive text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`}
          >
            {l.toUpperCase()}
          </button>
        ))}
      </div>
      {me.data && <span className="hidden text-xs text-muted-foreground sm:inline">{me.data.email}</span>}
      <Button
        variant="ghost"
        size="sm"
        onClick={async () => { await endpoints.logout(); router.push("/login?force=1"); router.refresh(); }}
      >
        <LogOut className="size-4" />{t("sign_out")}
      </Button>
    </header>
  );
}
