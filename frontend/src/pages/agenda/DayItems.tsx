import { Trash2 } from "lucide-react";
import { Link } from "react-router";
import type { CalendarEventItem, CalendarItem } from "@/api/types";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { formatMoney, formatTimeRange, monthOf } from "@/lib/format";
import { CALENDAR_KIND_LABELS, PET_EVENT_TYPE_LABELS, TASK_PRIORITY_LABELS } from "@/lib/labels";
import { EventDetails } from "./EventDetails";
import { KIND_TONES, KindDot } from "./kinds";
import type { EventToDelete } from "./queries";

const titleClass = "max-w-full text-left font-medium break-words text-slate-900 underline-offset-2 hover:underline";

/** Page of the module that owns a read-only item: the agenda only shows it. */
function linkOf(item: Exclude<CalendarItem, CalendarEventItem>): string {
  switch (item.kind) {
    case "task":
      return `/tarefas?${new URLSearchParams({ q: item.title })}`;
    case "bill":
      return `/financas?month=${monthOf(item.date)}`;
    case "pet":
      return `/pets/${item.pet_id}`;
  }
}

function Details({ item }: { item: CalendarItem }) {
  switch (item.kind) {
    case "event":
      return <EventDetails location={item.location} recurrence={item.recurrence} />;
    case "task":
      return (
        <span>
          Prioridade {TASK_PRIORITY_LABELS[item.priority].toLowerCase()}
          {item.status === "doing" && " · em andamento"}
        </span>
      );
    case "bill":
      return (
        <span>
          {formatMoney(item.amount)} · {item.category}
        </span>
      );
    case "pet":
      return (
        <span>
          {PET_EVENT_TYPE_LABELS[item.type]}
          {item.description && ` · ${item.description}`}
        </span>
      );
  }
}

export interface DayItemsProps {
  items: readonly CalendarItem[];
  onEdit: (eventId: string) => void;
  onDelete: (event: EventToDelete) => void;
}

/**
 * Items of one day. Events open the form and can be deleted; tasks, bills and pet reminders are
 * read-only here and link to their module.
 */
export function DayItems({ items, onEdit, onDelete }: DayItemsProps) {
  return (
    <ul className="divide-y divide-slate-100">
      {items.map((item) => (
        <li key={`${item.kind}-${item.id}`} className="flex items-start gap-3 py-3">
          <span className="w-24 shrink-0 pt-0.5 text-sm font-medium text-slate-800">
            {formatTimeRange(item.time, item.kind === "event" ? item.end_time : null)}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex items-start gap-2">
              <KindDot kind={item.kind} className="mt-2" />
              {item.kind === "event" ? (
                <button type="button" onClick={() => onEdit(item.id)} className={titleClass}>
                  {item.title}
                </button>
              ) : (
                <Link to={linkOf(item)} className={titleClass}>
                  {item.title}
                </Link>
              )}
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 pl-4 text-sm text-slate-700">
              {item.kind !== "event" && <Badge tone={KIND_TONES[item.kind]}>{CALENDAR_KIND_LABELS[item.kind]}</Badge>}
              <Details item={item} />
            </div>
          </div>
          {item.kind === "event" && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onDelete({ id: item.id, title: item.title, recurrence: item.recurrence })}
              aria-label={`Excluir ${item.title}`}
              className="shrink-0 text-red-700 hover:bg-red-50"
            >
              <Trash2 aria-hidden="true" className="size-4" />
            </Button>
          )}
        </li>
      ))}
    </ul>
  );
}
