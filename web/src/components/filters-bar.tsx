"use client";
import type { Filter, I18nInfo } from "@/lib/api";
import { useLabelMaps } from "@/components/chart-card";
import { useT } from "@/lib/i18n";
import { DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { ChevronDown, X } from "lucide-react";

export type Selections = Record<string, string[] | string>;

export function FiltersBar({ filters, selections, onChange, i18n }: {
  filters: Filter[]; selections: Selections; onChange: (s: Selections) => void; i18n?: I18nInfo;
}) {
  const t = useT();
  const { LV } = useLabelMaps(i18n);
  if (!filters.length) return null;
  const active = Object.values(selections).some((v) => (Array.isArray(v) ? v.length : !!v));

  return (
    <div className="flex flex-wrap items-center gap-2">
      {filters.map((f) => {
        if (f.type === "single") {
          const cur = (selections[f.id] as string) || f.resolved_options[0];
          return (
            <div key={f.id} className="inline-flex overflow-hidden rounded-lg border border-border text-xs">
              {f.resolved_options.map((opt) => (
                <button key={opt} type="button" onClick={() => onChange({ ...selections, [f.id]: opt })}
                  className={`px-3 py-1.5 transition-colors ${cur === opt ? "grad-olive font-bold text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`}>
                  {String(LV(opt))}
                </button>
              ))}
            </div>
          );
        }
        const sel = (selections[f.id] as string[]) ?? [];
        return (
          <DropdownMenu key={f.id}>
            <DropdownMenuTrigger render={<Button variant="outline" size="sm" className={sel.length ? "border-olive/60" : ""} />}>
              {f.label}
              {sel.length > 0 && <span className="rounded-full bg-olive px-1.5 text-[10px] font-extrabold text-primary-foreground">{sel.length}</span>}
              <ChevronDown className="size-3.5 opacity-60" />
            </DropdownMenuTrigger>
            <DropdownMenuContent className="max-h-80 w-64 overflow-auto">
              {f.resolved_options.map((opt) => (
                <DropdownMenuCheckboxItem key={opt} checked={sel.includes(opt)}
                  onSelect={(e) => e.preventDefault()}
                  onCheckedChange={(on) => onChange({ ...selections, [f.id]: on ? [...sel, opt] : sel.filter((x) => x !== opt) })}>
                  {String(LV(opt))}
                </DropdownMenuCheckboxItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        );
      })}
      {active && (
        <Button variant="ghost" size="sm" onClick={() => onChange({})}><X className="size-3.5" />{t("clear")}</Button>
      )}
    </div>
  );
}
