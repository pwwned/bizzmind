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
import { useState } from "react";
import { ArrowLeft, CircleUserRound, CreditCard, LogOut, Pencil, Wallet } from "lucide-react";
import { Input } from "@/components/ui/input";
import { ThemeToggle } from "@/lib/theme";
import { CreditsChip } from "@/components/credits-chip";

export function AppHeader({ crumb, back, plain = false, onRename }: {
  crumb?: string; back?: boolean; plain?: boolean; onRename?: (name: string) => void;
}) {
  const t = useT();
  const [editing, setEditing] = useState<string | null>(null);
  const { lang, setLang } = useLang();
  const me = useQuery({ queryKey: ["me"], queryFn: endpoints.me, staleTime: 5 * 60_000 });
  const initial = (me.data?.email?.[0] ?? "•").toUpperCase();

  return (
    <header className={`flex items-center gap-4 border-b border-border bg-background px-6 py-3 ${plain ? "" : "sticky top-0 z-40"}`}>
      <Link href="/app" className="shrink-0"><Logo size={28} /></Link>
      {crumb && (editing !== null ? (
        <form className="flex items-center gap-1.5" onSubmit={(e) => {
          e.preventDefault();
          if (editing.trim() && editing.trim() !== crumb) onRename?.(editing.trim());
          setEditing(null);
        }}>
          <Input autoFocus value={editing} onChange={(e) => setEditing(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Escape") setEditing(null); }}
            onBlur={() => setEditing(null)} className="h-8 w-56 text-sm font-semibold" />
        </form>
      ) : (
        <span className="truncate text-sm text-muted-foreground">
          /{" "}
          {onRename ? (
            <button type="button" onClick={() => setEditing(crumb)} title={t("rename_project")}
              className="group/name inline-flex items-center gap-1.5 font-semibold text-foreground hover:text-olive">
              {crumb}
              <Pencil className="size-3 opacity-0 transition-opacity group-hover/name:opacity-60" />
            </button>
          ) : <b className="font-semibold text-foreground">{crumb}</b>}
        </span>
      ))}
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
