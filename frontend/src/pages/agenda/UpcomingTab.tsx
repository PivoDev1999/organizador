import { CalendarClock } from "lucide-react";
import { useId } from "react";
import { errorMessage } from "@/api/errors";
import type { AgendaEvent, EventOccurrence } from "@/api/types";
import { Button } from "@/components/Button";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { SkeletonList } from "@/components/Spinner";
import { addDays, relativeDayLabel } from "@/lib/calendar";
import { formatDate, formatTimeRange } from "@/lib/format";
import { EventDetails } from "./EventDetails";
import { useEventOccurrences } from "./queries";

/** How far ahead "Próximos" looks, in days. */
export const UPCOMING_DAYS = 60;

function groupByDate(occurrences: readonly EventOccurrence[]): Array<[string, EventOccurrence[]]> {
  const groups = new Map<string, EventOccurrence[]>();
  for (const occurrence of occurrences) {
    const list = groups.get(occurrence.date);
    if (list) list.push(occurrence);
    else groups.set(occurrence.date, [occurrence]);
  }
  return [...groups];
}

export interface UpcomingTabProps {
  today: string;
  onCreate: () => void;
  onEdit: (event: AgendaEvent) => void;
}

/** Occurrences from today to today + 60 days, grouped by day ("Hoje", "Amanhã", "Sexta, 07/11"). */
export function UpcomingTab({ today, onCreate, onEdit }: UpcomingTabProps) {
  const baseId = useId();
  const occurrences = useEventOccurrences({ from: today, to: addDays(today, UPCOMING_DAYS) });

  if (occurrences.isPending) return <SkeletonList rows={3} label="Carregando compromissos..." />;
  if (occurrences.isError) {
    return (
      <ErrorState
        title="Não foi possível carregar os compromissos"
        message={errorMessage(occurrences.error)}
        onRetry={() => void occurrences.refetch()}
      />
    );
  }
  if (occurrences.data.length === 0) {
    return (
      <EmptyState
        icon={CalendarClock}
        title="Nenhum compromisso nos próximos 60 dias."
        action={<Button onClick={onCreate}>Novo compromisso</Button>}
      />
    );
  }

  return (
    <div className="space-y-4">
      {groupByDate(occurrences.data).map(([date, items]) => (
        <section key={date} aria-labelledby={`${baseId}-${date}`}>
          <h3 id={`${baseId}-${date}`} className="flex items-baseline gap-2 border-b border-slate-200 pb-1 font-semibold text-slate-900">
            {relativeDayLabel(date, today)}
            {(date === today || date === addDays(today, 1)) && (
              <span className="text-sm font-normal text-slate-700">{formatDate(date)}</span>
            )}
          </h3>
          <ul className="divide-y divide-slate-100">
            {items.map(({ event }) => (
              <li key={event.id} className="flex items-start gap-3 py-3">
                <span className="w-24 shrink-0 pt-0.5 text-sm font-medium text-slate-800">
                  {formatTimeRange(event.start_time, event.end_time)}
                </span>
                <div className="min-w-0 flex-1">
                  <button
                    type="button"
                    onClick={() => onEdit(event)}
                    className="max-w-full text-left font-medium break-words text-slate-900 underline-offset-2 hover:underline"
                  >
                    {event.title}
                  </button>
                  {(event.location || event.recurrence !== "none") && (
                    <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-sm text-slate-700">
                      <EventDetails location={event.location} recurrence={event.recurrence} />
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
