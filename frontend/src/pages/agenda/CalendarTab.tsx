import { CalendarPlus } from "lucide-react";
import { useId, useMemo } from "react";
import { errorMessage } from "@/api/errors";
import type { CalendarItem } from "@/api/types";
import { Button } from "@/components/Button";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { MonthNavigator } from "@/components/MonthNavigator";
import { SkeletonList } from "@/components/Spinner";
import { monthGridDays } from "@/lib/calendar";
import { formatLongDate } from "@/lib/format";
import { DayItems } from "./DayItems";
import { KindLegend } from "./kinds";
import { MonthGrid } from "./MonthGrid";
import { useCalendar, type EventToDelete } from "./queries";

const NOTHING = new Map<string, CalendarItem[]>();

function groupByDay(items: readonly CalendarItem[]): Map<string, CalendarItem[]> {
  const byDay = new Map<string, CalendarItem[]>();
  for (const item of items) {
    const list = byDay.get(item.date);
    if (list) list.push(item);
    else byDay.set(item.date, [item]);
  }
  return byDay;
}

export interface CalendarTabProps {
  month: string;
  selected: string;
  today: string;
  onChangeMonth: (month: string) => void;
  onSelectDay: (day: string) => void;
  onCreate: (day: string) => void;
  onEdit: (eventId: string) => void;
  onDelete: (event: EventToDelete) => void;
}

/** Month grid fed by GET /api/calendar for the days on screen, plus the list of the selected day. */
export function CalendarTab({
  month,
  selected,
  today,
  onChangeMonth,
  onSelectDay,
  onCreate,
  onEdit,
  onDelete,
}: CalendarTabProps) {
  const titleId = useId();
  const days = useMemo(() => monthGridDays(month), [month]);
  const range = { from: days[0] ?? `${month}-01`, to: days.at(-1) ?? `${month}-01` };
  const calendar = useCalendar(range);
  const itemsByDay = useMemo(() => groupByDay(calendar.data ?? []), [calendar.data]);
  // While another month loads, the previous one's data is still in the query: no markers or list for
  // the new month yet. After an error, the old data is not shown either.
  const stale = calendar.isPlaceholderData;
  const dayItems = itemsByDay.get(selected) ?? [];

  let dayContent;
  if (calendar.isPending || stale) {
    dayContent = <SkeletonList rows={2} label="Carregando a agenda..." />;
  } else if (calendar.isError) {
    dayContent = (
      <ErrorState
        title="Não foi possível carregar a agenda"
        message={errorMessage(calendar.error)}
        onRetry={() => void calendar.refetch()}
      />
    );
  } else if (dayItems.length === 0) {
    dayContent = (
      <EmptyState
        icon={CalendarPlus}
        title="Nada marcado para este dia."
        action={
          <Button variant="secondary" onClick={() => onCreate(selected)}>
            Novo compromisso
          </Button>
        }
      />
    );
  } else {
    dayContent = <DayItems items={dayItems} onEdit={onEdit} onDelete={onDelete} />;
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
      <div className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <MonthNavigator month={month} onChange={onChangeMonth} />
          <KindLegend />
        </div>
        <MonthGrid
          month={month}
          days={days}
          itemsByDay={stale || calendar.isError ? NOTHING : itemsByDay}
          selected={selected}
          today={today}
          onSelect={onSelectDay}
          busy={calendar.isFetching}
        />
      </div>
      <section aria-labelledby={titleId} className="border-t border-slate-200 pt-4 lg:border-t-0 lg:pt-0">
        <h2 id={titleId} className="mb-1 text-lg font-semibold text-slate-900 first-letter:uppercase">
          {formatLongDate(selected)}
          {selected === today && <span className="font-normal text-slate-700"> (hoje)</span>}
        </h2>
        {dayContent}
      </section>
    </div>
  );
}
