"use client";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { beginLogout, endpoints } from "@/lib/api";
import { useLang, useT } from "@/lib/i18n";
import { Logo } from "@/components/logo";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuGroup, DropdownMenuItem,
  DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ArrowLeft, CircleUserRound, CreditCard, LogOut, Wallet } from "lucide-react";
import { ThemeToggle } from "@/lib/theme";
import { useChromeHidden } from "@/lib/use-chrome-visibility";
import { CreditsChip } from "@/components/credits-chip";

export function AppHeader({ crumb, back, autoHide = false }: { crumb?: string; back?: boolean; autoHide?: boolean }) {
  const hidden = useChromeHidden() && autoHide;
  const t = useT();
  const { lang, setLang } = useLang();
  const me = useQuery({ queryKey: ["me"], queryFn: endpoints.me, staleTime: 5 * 60_000 });
  const initial = (me.data?.email?.[0] ?? "•").toUpperCase();

  return (
    <header className={`sticky top-0 z-40 flex items-center gap-4 border-b border-border bg-background px-6 py-3 transition-transform duration-300 ${hidden ? "-translate-y-full" : "translate-y-0"}`}>
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
      <ThemeToggle />
      <CreditsChip />
      <DropdownMenu>
        <DropdownMenuTrigger
          className="inline-flex size-8 items-center justify-center rounded-full border border-olive/40 bg-olive/10 text-[13px] font-extrabold text-olive transition-colors hover:bg-olive/20"
          title={me.data?.email ?? ""}
        >
          {initial}
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="min-w-56">
          <DropdownMenuGroup>
            <DropdownMenuLabel className="truncate text-xs font-normal text-muted-foreground">
              {me.data?.email ?? "…"}
            </DropdownMenuLabel>
          </DropdownMenuGroup>
          <DropdownMenuSeparator />
          <DropdownMenuItem nativeButton={false} render={<Link href="/account" />}>
            <CircleUserRound className="size-4" />{t("account_settings")}
          </DropdownMenuItem>
          <DropdownMenuItem nativeButton={false} render={<Link href="/pricing" />}>
            <Wallet className="size-4" />{t("usage_billing")}
          </DropdownMenuItem>
          <DropdownMenuItem nativeButton={false} render={<Link href="/billing" />}>
            <CreditCard className="size-4" />{t("billing_title")}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            variant="destructive"
            onClick={async () => {
              beginLogout();                       // a concurrent 401 must not hijack navigation
              try { await endpoints.logout(); } catch { /* cookies may already be gone */ }
              window.location.assign("/");         // hard reload: clears all client state
            }}
          >
            <LogOut className="size-4" />{t("sign_out")}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </header>
  );
}
