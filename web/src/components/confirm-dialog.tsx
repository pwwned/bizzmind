"use client";
/* In-app confirmation dialog (replaces browser confirm()). Usage:
   const confirm = useConfirm();
   if (await confirm({ title, description, actionLabel, destructive })) { … }
   Mount <ConfirmHost /> once (Providers does it). */
import { createContext, useCallback, useContext, useRef, useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { useT } from "@/lib/i18n";

export interface ConfirmOptions {
  title: string;
  description?: string;
  actionLabel?: string;
  destructive?: boolean;
}

const ConfirmContext = createContext<(o: ConfirmOptions) => Promise<boolean>>(() => Promise.resolve(false));

export function useConfirm() {
  return useContext(ConfirmContext);
}

export function ConfirmProvider({ children }: { children: React.ReactNode }) {
  const t = useT();
  const [opts, setOpts] = useState<ConfirmOptions | null>(null);
  const resolver = useRef<(v: boolean) => void>(null);

  const confirm = useCallback((o: ConfirmOptions) => {
    setOpts(o);
    return new Promise<boolean>((resolve) => { resolver.current = resolve; });
  }, []);

  const close = (v: boolean) => {
    resolver.current?.(v);
    resolver.current = null;
    setOpts(null);
  };

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      <Dialog open={!!opts} onOpenChange={(open) => { if (!open) close(false); }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{opts?.title}</DialogTitle>
            {opts?.description && <DialogDescription>{opts.description}</DialogDescription>}
          </DialogHeader>
          <DialogFooter className="gap-2">
            <Button variant="ghost" onClick={() => close(false)}>{t("cancel")}</Button>
            <Button
              className={opts?.destructive ? "bg-destructive text-white hover:bg-destructive/90" : "grad-olive text-primary-foreground"}
              onClick={() => close(true)}
            >
              {opts?.actionLabel ?? "OK"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </ConfirmContext.Provider>
  );
}
