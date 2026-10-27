import { ChevronLeft, ChevronRight } from "lucide-react";
import { formatMonthName, shiftMonth } from "@/lib/calendar";
import { Button } from "./Button";

export interface MonthNavigatorProps {
  /** "YYYY-MM". */
  month: string;
  onChange: (month: string) => void;
}

/** Previous / next month with the month's name in pt-BR, announced when it changes. */
export function MonthNavigator({ month, onChange }: MonthNavigatorProps) {
  const name = formatMonthName(month);
  return (
    <div className="flex items-center gap-1" role="group" aria-label="Mês">
      <Button variant="secondary" size="sm" onClick={() => onChange(shiftMonth(month, -1))} aria-label="Mês anterior">
        <ChevronLeft aria-hidden="true" className="size-5" />
      </Button>
      <p aria-live="polite" className="min-w-40 text-center text-lg font-semibold text-slate-900">
        {name}
      </p>
      <Button variant="secondary" size="sm" onClick={() => onChange(shiftMonth(month, 1))} aria-label="Próximo mês">
        <ChevronRight aria-hidden="true" className="size-5" />
      </Button>
    </div>
  );
}
