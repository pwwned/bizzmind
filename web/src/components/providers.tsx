"use client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { LangContext, readLang, writeLang, type Lang } from "@/lib/i18n";
import { ThemeContext, readTheme, writeTheme, type Theme } from "@/lib/theme";
import { Toaster } from "@/components/ui/sonner";
import { ConfirmProvider } from "@/components/confirm-dialog";
import { BuyCreditsProvider } from "@/components/buy-credits";

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(() => new QueryClient({
    defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 15_000 } },
  }));
  const [lang, setLangState] = useState<Lang>("bg");
  const [theme, setThemeState] = useState<Theme>("dark");
  useEffect(() => {
    const l = readLang();
    setLangState(l);
    document.documentElement.lang = l;
    const th = readTheme();
    setThemeState(th);
    document.documentElement.classList.toggle("dark", th === "dark");
  }, []);
  const setTheme = (th: Theme) => {
    writeTheme(th);
    setThemeState(th);
    document.documentElement.classList.toggle("dark", th === "dark");
  };
  const setLang = (l: Lang) => {
    writeLang(l);
    setLangState(l);
    document.documentElement.lang = l;
    // the API caches per language (translated content, AI output) — start clean
    client.invalidateQueries();
  };
  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>
      <LangContext.Provider value={{ lang, setLang }}>
        <QueryClientProvider client={client}>
          <ConfirmProvider><BuyCreditsProvider>{children}</BuyCreditsProvider></ConfirmProvider>
          <Toaster richColors position="bottom-right" theme={theme} />
        </QueryClientProvider>
      </LangContext.Provider>
    </ThemeContext.Provider>
  );
}
