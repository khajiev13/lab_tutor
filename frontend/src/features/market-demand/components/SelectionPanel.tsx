import { useState, useCallback } from "react";
import { CheckSquare, Square, Send } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

export interface SelectionItem {
  id: string;
  label: string;
  description?: string;
  badge?: string;
  count?: number;
  /** Lines shown in a tooltip on hover (e.g. individual job titles) */
  tooltipLines?: string[];
}

interface SelectionCardProps {
  title: string;
  subtitle?: string;
  items: SelectionItem[];
  onConfirm: (selectedIds: string[]) => void;
  disabled?: boolean;
  /** Set to true once teacher has confirmed — renders as a static summary */
  confirmed?: boolean;
  confirmedIds?: string[];
}

export function SelectionCard({
  title,
  subtitle,
  items,
  onConfirm,
  disabled,
  confirmed,
  confirmedIds,
}: SelectionCardProps) {
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const allSelected = selected.size === items.length && items.length > 0;
  const someSelected = selected.size > 0;

  const toggleAll = useCallback(() => {
    setSelected((prev) => {
      if (prev.size === items.length) return new Set();
      return new Set(items.map((i) => i.id));
    });
  }, [items]);

  const toggle = useCallback((id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const handleConfirm = useCallback(() => {
    if (selected.size === 0) return;
    onConfirm(Array.from(selected));
  }, [selected, onConfirm]);

  // ── Confirmed state: show a compact summary ──
  if (confirmed && confirmedIds) {
    const confirmedItems = items.filter((i) => confirmedIds.includes(i.id));
    return (
      <div className="rounded-lg border bg-card p-3 space-y-2 w-full">
        <p className="text-xs font-semibold text-muted-foreground">{title}</p>
        <div className="flex flex-wrap gap-1">
          {confirmedItems.map((item) => (
            <Badge key={item.id} variant="secondary" className="text-xs">
              {item.label}
              {item.count != null && (
                <span className="ml-1 opacity-60">({item.count})</span>
              )}
            </Badge>
          ))}
        </div>
        <p className="text-[10px] text-emerald-600">
          ✓ {confirmedItems.length} selected
        </p>
      </div>
    );
  }

  // ── Interactive state: checkboxes + confirm ──
  return (
    <div className="rounded-lg border bg-card p-3 space-y-3 w-full">
      <div>
        <p className="text-sm font-semibold text-foreground">{title}</p>
        {subtitle && (
          <p className="text-xs text-muted-foreground mt-0.5">{subtitle}</p>
        )}
      </div>

      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={toggleAll}
          disabled={disabled}
          className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
        >
          {allSelected ? (
            <Square className="size-3.5" />
          ) : (
            <CheckSquare className="size-3.5" />
          )}
          {allSelected ? "Deselect all" : "Select all"}
        </button>
        {someSelected && (
          <span className="text-xs text-muted-foreground">
            {selected.size} selected
          </span>
        )}
      </div>

      <TooltipProvider>
        <div className="space-y-1 max-h-64 overflow-y-auto">
          {items.map((item) => {
            const checked = selected.has(item.id);
            const row = (
              <label
                key={item.id}
                className="flex items-center gap-2.5 py-1.5 px-2 rounded-md cursor-pointer hover:bg-muted/50 transition-colors"
              >
                <Checkbox
                  checked={checked}
                  onCheckedChange={() => toggle(item.id)}
                  disabled={disabled}
                  className="shrink-0"
                />
                <span className="text-sm text-foreground flex-1 min-w-0 truncate">
                  {item.label}
                </span>
                {item.badge && (
                  <Badge
                    variant="outline"
                    className="text-[10px] px-1.5 py-0 shrink-0"
                  >
                    {item.badge}
                  </Badge>
                )}
                {item.count != null && (
                  <span className="text-xs text-muted-foreground shrink-0">
                    {item.count} jobs
                  </span>
                )}
              </label>
            );

            if (!item.tooltipLines?.length) {
              return <div key={item.id}>{row}</div>;
            }

            return (
              <Tooltip key={item.id}>
                <TooltipTrigger asChild>
                  <div>{row}</div>
                </TooltipTrigger>
                <TooltipContent
                  side="right"
                  align="start"
                  className="max-w-xs space-y-0.5 p-2"
                >
                  {item.tooltipLines.map((line, i) => (
                    <p key={i} className="text-xs">{line}</p>
                  ))}
                </TooltipContent>
              </Tooltip>
            );
          })}
        </div>
      </TooltipProvider>

      <Button
        size="sm"
        className="w-full gap-1.5"
        disabled={!someSelected || disabled}
        onClick={handleConfirm}
      >
        <Send className="size-3" />
        Confirm Selection
        {someSelected && (
          <span className="ml-1 text-xs opacity-70">({selected.size})</span>
        )}
      </Button>
    </div>
  );
}
