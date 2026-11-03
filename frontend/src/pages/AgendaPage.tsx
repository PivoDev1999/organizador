import { Plus } from "lucide-react";
import { useState } from "react";
import type { AgendaEvent } from "@/api/types";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { PageHeader } from "@/components/PageHeader";
import { Tabs } from "@/components/Tabs";
import { useToday } from "@/hooks/useToday";
import { useUrlFilters } from "@/hooks/useUrlFilters";
import { defaultDayOf, parseDate, parseMonth } from "@/lib/calendar";
import { monthOf } from "@/lib/format";
import { CalendarTab } from "./agenda/CalendarTab";
import { EventEditModal, EventFormModal } from "./agenda/EventFormModal";
import { useDeleteEvent, type EventToDelete } from "./agenda/queries";
import { UpcomingTab } from "./agenda/UpcomingTab";

type Tab = "calendar" | "upcoming";
const TABS = [
  { value: "calendar", label: "Calendário" },
  { value: "upcoming", label: "Próximos" },
] as const satisfies ReadonlyArray<{ value: Tab; label: string }>;

/**
 * null: closed. "new" carries the date to suggest; editing from the calendar has only the id (the
 * form loads the event), from "Próximos" the whole event.
 */
type Editing =
  | { mode: "new"; date: string }
  | { mode: "edit"; id: string }
  | { mode: "edit"; event: AgendaEvent }
  | null;

function deleteMessage(event: EventToDelete): string {
  const base = `"${event.title}" e os anexos dele serão excluídos.`;
  return event.recurrence === "none" ? base : `${base} Este compromisso se repete: todas as repetições serão excluídas.`;
}

/**
 * Agenda: month calendar with everything that falls on each day (events, tasks, bills, pet reminders)
 * and the next events. The URL keeps the tab, the month (`month=YYYY-MM`) and the selected day
 * (`day=YYYY-MM-DD`); by default, the current month and today, or the 1st of another month.
 */
export function AgendaPage() {
  const url = useUrlFilters();
  const today = useToday();
  const tab = url.getEnum<Tab>("tab", ["calendar", "upcoming"], "calendar");
  const month = parseMonth(url.params.get("month")) ?? monthOf(today);
  const day = parseDate(url.params.get("day"));
  const selected = day?.startsWith(month) ? day : defaultDayOf(month, today);
  const [editing, setEditing] = useState<Editing>(null);
  const [deleting, setDeleting] = useState<EventToDelete | null>(null);
  const remove = useDeleteEvent();

  const askDelete = (event: AgendaEvent) => {
    setEditing(null);
    setDeleting({ id: event.id, title: event.title, recurrence: event.recurrence });
  };

  return (
    <>
      <PageHeader
        title="Agenda"
        actions={
          <Button onClick={() => setEditing({ mode: "new", date: tab === "calendar" ? selected : today })}>
            <Plus aria-hidden="true" className="size-5" />
            Novo compromisso
          </Button>
        }
      />
      <Card>
        <Tabs label="Agenda" tabs={TABS} value={tab} onChange={(next) => url.update({ tab: next === "calendar" ? null : next })}>
          {tab === "calendar" ? (
            <CalendarTab
              month={month}
              selected={selected}
              today={today}
              onChangeMonth={(next) => url.update({ month: next, day: null })}
              // A day of the neighbor months (first and last weeks) also moves the calendar there.
              onSelectDay={(next) => url.update({ month: monthOf(next), day: next })}
              onCreate={(date) => setEditing({ mode: "new", date })}
              onEdit={(id) => setEditing({ mode: "edit", id })}
              onDelete={setDeleting}
            />
          ) : (
            <UpcomingTab
              today={today}
              onCreate={() => setEditing({ mode: "new", date: today })}
              onEdit={(event) => setEditing({ mode: "edit", event })}
            />
          )}
        </Tabs>
      </Card>

      {editing?.mode === "new" && (
        <EventFormModal event={null} defaultDate={editing.date} onClose={() => setEditing(null)} />
      )}
      {editing?.mode === "edit" &&
        ("event" in editing ? (
          <EventFormModal
            event={editing.event}
            defaultDate={editing.event.starts_on}
            onClose={() => setEditing(null)}
            onDelete={askDelete}
          />
        ) : (
          <EventEditModal eventId={editing.id} onClose={() => setEditing(null)} onDelete={askDelete} />
        ))}
      {deleting && (
        <ConfirmDialog
          title="Excluir compromisso?"
          message={deleteMessage(deleting)}
          loading={remove.isPending}
          onConfirm={() => remove.mutate(deleting, { onSettled: () => setDeleting(null) })}
          onCancel={() => setDeleting(null)}
        />
      )}
    </>
  );
}
