import type { CalendarItem } from "@/api/types";
import { cn } from "@/lib/cn";
import { formatMonthName } from "@/lib/calendar";
import { formatLongDate } from "@/lib/format";
import { WEEKDAY_SHORT } from "@/lib/labels";
import { describeItems, KindDot, kindsOf } from "./kinds";

const NO_ITEMS: CalendarItem[] = [];

export interface MonthGridProps {
  /** "YYYY-MM" shown; days of the neighbor months fill the first and last weeks. */
  month: string;
  /** Whole weeks, Sunday first (see monthGridDays). */
  days: readonly string[];
  itemsByDay: ReadonlyMap<string, CalendarItem[]>;
  selected: string;
  today: string;
  onSelect: (day: string) => void;
  busy?: boolean;
}

/** Month view: one button per day with colored markers by kind; today and the selected day stand out. */
export function MonthGrid({ month, days, itemsByDay, selected, today, onSelect, busy }: MonthGridProps) {
  return (
    <div role="group" aria-label={`Calendário de ${formatMonthName(month)}`} aria-busy={busy || undefined}>
      <div aria-hidden="true" className="grid grid-cols-7 pb-1 text-center text-xs font-medium text-slate-600">
        {WEEKDAY_SHORT.map((name) => (
          <span key={name}>{name}</span>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-1">
        {days.map((day) => {
          const items = itemsByDay.get(day) ?? NO_ITEMS;
          const inMonth = day.startsWith(month);
          const isToday = day === today;
          const isSelected = day === selected;
          const label = `${formatLongDate(day)} de ${day.slice(0, 4)}${isToday ? ", hoje" : ""}: ${describeItems(items)}`;
          return (
            <button
              key={day}
              type="button"
              aria-label={label}
              aria-pressed={isSelected}
              aria-current={isToday ? "date" : undefined}
              onClick={() => onSelect(day)}
              className={cn(
                "flex min-h-12 flex-col items-center gap-1 rounded-lg border p-1 sm:min-h-20 sm:items-start sm:p-2",
                isSelected
                  ? "border-brand-700 bg-brand-50 ring-1 ring-brand-700"
                  : "border-slate-200 hover:bg-slate-50",
                !inMonth && !isSelected && "bg-slate-50",
              )}
            >
              <span
                className={cn(
                  "flex size-7 items-center justify-center rounded-full text-sm",
                  isToday ? "bg-brand-700 font-semibold text-white" : inMonth ? "text-slate-900" : "text-slate-500",
                )}
              >
                {Number(day.slice(8))}
              </span>
              <span className="flex flex-wrap justify-center gap-1">
                {kindsOf(items).map((kind) => (
                  <KindDot key={kind} kind={kind} />
                ))}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
