"use client";
/* In-app confirmation dialog (replaces browser confirm()). Usage:
   const confirm = useConfirm();
   if (await confirm({ title, description, actionLabel, destructive })) { … }
   Mount <ConfirmHost /> once (Providers does it). */
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { useT } from "@/lib/i18n";

export interface ConfirmOptions {
  title: string;
  description?: string;
  actionLabel?: string;
  destructive?: boolean;
  /** When set, the action unlocks only after the user types this exact text. */
  confirmText?: string;
  confirmHint?: string;
}

const ConfirmContext = createContext<(o: ConfirmOptions) => Promise<boolean>>(() => Promise.resolve(false));

export function useConfirm() {
  return useContext(ConfirmContext);
}

export function ConfirmProvider({ children }: { children: React.ReactNode }) {
  const t = useT();
  const [opts, setOpts] = useState<ConfirmOptions | null>(null);
  const [typed, setTyped] = useState("");
  useEffect(() => { if (opts) setTyped(""); }, [opts]);
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
          {opts?.confirmText && (
            <div className="flex flex-col gap-1.5">
              <div className="text-[12px] text-muted-foreground">{opts.confirmHint}</div>
              <Input autoFocus value={typed} onChange={(e) => setTyped(e.target.value)} placeholder={opts.confirmText} />
            </div>
          )}
          <DialogFooter className="gap-2">
            <Button variant="ghost" onClick={() => close(false)}>{t("cancel")}</Button>
            <Button
              className={opts?.destructive ? "bg-destructive text-white hover:bg-destructive/90" : "grad-olive text-primary-foreground"}
              disabled={!!opts?.confirmText && typed.trim().toLowerCase() !== opts.confirmText.trim().toLowerCase()}
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
