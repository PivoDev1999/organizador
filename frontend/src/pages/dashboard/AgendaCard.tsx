import { CalendarDays, MapPin } from "lucide-react";
import type { Dashboard } from "@/api/types";
import { PreviewList } from "@/components/PreviewList";
import { SectionCard } from "@/components/SectionCard";
import { relativeDayLabel } from "@/lib/calendar";
import { formatTimeRange } from "@/lib/format";

export interface AgendaCardProps {
  upcoming: Dashboard["agenda"]["upcoming"];
  /** The device's today (as on the agenda page), for "Hoje" and "Amanhã". */
  today: string;
}

export function AgendaCard({ upcoming, today }: AgendaCardProps) {
  return (
    <SectionCard title="Agenda" icon={CalendarDays} to="/agenda" linkLabel="Ver agenda">
      {upcoming.total === 0 ? (
        <p className="text-slate-700">Nenhum compromisso nos próximos 7 dias.</p>
      ) : (
        <PreviewList
          items={upcoming.items}
          total={upcoming.total}
          // A recurring event shows up once per day: the day completes the key.
          getKey={({ date, event }) => `${event.id}-${date}`}
          renderItem={({ date, event }) => (
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="break-words font-medium text-slate-900">{event.title}</p>
                {event.location && (
                  <p className="flex items-center gap-1 text-sm text-slate-700">
                    <MapPin aria-hidden="true" className="size-4 shrink-0" />
                    <span className="sr-only">Local:</span>
                    <span className="min-w-0 break-words">{event.location}</span>
                  </p>
                )}
              </div>
              <div className="flex shrink-0 flex-col items-end text-sm">
                <time dateTime={date} className="font-medium text-slate-900">
                  {relativeDayLabel(date, today)}
                </time>
                <span className="text-slate-700">{formatTimeRange(event.start_time, event.end_time)}</span>
              </div>
            </div>
          )}
          moreLabel={(n) => `e mais ${n} compromissos`}
        />
      )}
    </SectionCard>
  );
}
