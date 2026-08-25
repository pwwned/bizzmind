"use client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { LangContext, readLang, writeLang, type Lang } from "@/lib/i18n";
import { Toaster } from "@/components/ui/sonner";

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(() => new QueryClient({
    defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 15_000 } },
  }));
  const [lang, setLangState] = useState<Lang>("bg");
  useEffect(() => {
    const l = readLang();
    setLangState(l);
    document.documentElement.lang = l;
    document.documentElement.classList.add("dark");
  }, []);
  const setLang = (l: Lang) => {
    writeLang(l);
    setLangState(l);
    document.documentElement.lang = l;
    // the API caches per language (translated content, AI output) — start clean
    client.invalidateQueries();
  };
  return (
    <LangContext.Provider value={{ lang, setLang }}>
      <QueryClientProvider client={client}>
        {children}
        <Toaster richColors position="bottom-right" />
      </QueryClientProvider>
    </LangContext.Provider>
  );
}
