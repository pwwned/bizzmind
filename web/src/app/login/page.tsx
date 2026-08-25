"use client";
import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { endpoints, ApiError } from "@/lib/api";
import { useLang, useT } from "@/lib/i18n";
import { Logo } from "@/components/logo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ThemeToggle } from "@/lib/theme";

function LoginForm() {
  const t = useT();
  const { lang, setLang } = useLang();
  const router = useRouter();
  const params = useSearchParams();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(""); setNotice("");
    try {
      if (mode === "register") {
        if (password.length < 8) throw new Error(t("password_short"));
        const r = await endpoints.register(email, password, name);
        if (!r.confirmed) { setNotice(r.message ?? ""); setMode("login"); return; }
      } else {
        await endpoints.login(email, password);
      }
      router.push(params.get("next") ?? "/app");
      router.refresh();
    } catch (err) {
      setError(err instanceof ApiError || err instanceof Error ? err.message : t("login_failed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-6">
      <form onSubmit={submit} className="relative w-full max-w-sm rounded-2xl border border-border bg-card/80 p-8 shadow-2xl backdrop-blur">
        <div className="absolute left-4 top-4"><ThemeToggle /></div>
        <div className="absolute right-4 top-4 inline-flex overflow-hidden rounded-lg border border-border text-[11px] font-extrabold">
          {(["bg", "en"] as const).map((l) => (
            <button key={l} type="button" onClick={() => setLang(l)}
              className={`px-2.5 py-1.5 ${lang === l ? "grad-olive text-primary-foreground" : "text-muted-foreground"}`}>{l.toUpperCase()}</button>
          ))}
        </div>
        <div className="mb-6 flex flex-col items-center gap-3 text-center">
          <Logo size={40} />
          <p className="text-sm text-muted-foreground">{t(mode === "register" ? "register_sub" : "login_sub")}</p>
        </div>
        <div className="grid gap-4">
          <div className="grid gap-1.5">
            <Label htmlFor="email">{t("email")}</Label>
            <Input id="email" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          {mode === "register" && (
            <div className="grid gap-1.5">
              <Label htmlFor="name">{t("name_optional")}</Label>
              <Input id="name" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
          )}
          <div className="grid gap-1.5">
            <Label htmlFor="password">{t("password")}</Label>
            <Input id="password" type="password" required minLength={mode === "register" ? 8 : undefined}
              autoComplete={mode === "register" ? "new-password" : "current-password"}
              value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          {notice && <p className="text-sm text-olive">{notice}</p>}
          <Button type="submit" disabled={busy} className="grad-olive text-primary-foreground font-bold hover:opacity-90">
            {t(mode === "register" ? "register" : "sign_in")}
          </Button>
          <button type="button" className="text-xs text-muted-foreground underline-offset-4 hover:underline"
            onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); setNotice(""); }}>
            {t(mode === "login" ? "to_register" : "to_login")}
          </button>
        </div>
      </form>
    </main>
  );
}

export default function LoginPage() {
  return <Suspense><LoginForm /></Suspense>;
}
