"use client";
import { useT } from "@/lib/i18n";
import { Mark } from "@/components/logo";
import { Button } from "@/components/ui/button";
import { Upload } from "lucide-react";

export function DashboardEmpty({ onStart }: { onStart: () => void }) {
  const t = useT();
  const steps = [t("step_upload"), t("step_interview"), t("step_dashboard")];
  return (
    <div className="flex min-h-[55vh] flex-col items-center justify-center gap-5 text-center">
      <Mark size={56} className="opacity-90" />
      <h2 className="text-xl font-extrabold">{t("dash_empty_title")}</h2>
      <p className="max-w-lg text-sm leading-relaxed text-muted-foreground">{t("dash_empty_text")}</p>
      <ol className="flex flex-wrap items-center justify-center gap-4 text-[13px]">
        {steps.map((s, i) => (
          <li key={s} className={`flex items-center gap-2 ${i === 0 ? "text-foreground" : "text-muted-foreground"}`}>
            <b className={`inline-flex size-6 items-center justify-center rounded-lg text-xs ${i === 0 ? "grad-olive text-primary-foreground" : "border border-border"}`}>{i + 1}</b>
            {s}
          </li>
        ))}
      </ol>
      <Button onClick={onStart} className="grad-olive font-bold text-primary-foreground hover:opacity-90">
        <Upload className="size-4" />{t("start_upload")}
      </Button>
    </div>
  );
}

export function DashboardLoading() {
  const t = useT();
  return (
    <div className="flex min-h-[55vh] flex-col items-center justify-center gap-4 text-sm text-muted-foreground">
      <span className="size-9 animate-spin rounded-full border-[3px] border-border border-t-olive" />
      {t("loading_project")}
    </div>
  );
}
