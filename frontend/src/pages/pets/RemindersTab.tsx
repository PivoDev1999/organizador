import { BellRing, CalendarDays } from "lucide-react";
import { Link } from "react-router";
import { errorMessage } from "@/api/errors";
import type { PetReminder } from "@/api/types";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { SelectField } from "@/components/SelectField";
import { SkeletonList } from "@/components/Spinner";
import { useUrlFilters } from "@/hooks/useUrlFilters";
import { cn } from "@/lib/cn";
import { formatDate } from "@/lib/format";
import { PET_EVENT_TYPE_LABELS } from "@/lib/labels";
import { DEFAULT_REMINDER_WINDOW, REMINDER_WINDOWS, useReminders } from "./queries";

const WINDOW_OPTIONS = REMINDER_WINDOWS.map((days) => ({ value: String(days), label: `Próximos ${days} dias` }));

export interface RemindersTabProps {
  /** "Registrar agora": a new event of the same series, today, which resolves the reminder. */
  onRegister: (reminder: PetReminder) => void;
}

/** Next dates of vaccines, medicines etc. up to N days ahead; overdue ones always show up. */
export function RemindersTab({ onRegister }: RemindersTabProps) {
  const url = useUrlFilters();
  const within = Number(
    url.getEnum(
      "within",
      WINDOW_OPTIONS.map((o) => o.value),
      String(DEFAULT_REMINDER_WINDOW),
    ),
  );
  const reminders = useReminders(within);

  let content;
  if (reminders.isPending) {
    content = <SkeletonList rows={3} label="Carregando os lembretes..." />;
  } else if (reminders.isError) {
    content = (
      <ErrorState
        title="Não foi possível carregar os lembretes"
        message={errorMessage(reminders.error)}
        onRetry={() => void reminders.refetch()}
      />
    );
  } else if (reminders.data.length === 0) {
    content = (
      <EmptyState
        icon={BellRing}
        title={`Nenhum lembrete para os próximos ${within} dias.`}
        description="Os lembretes vêm da “próxima data” dos eventos dos pets."
      />
    );
  } else {
    content = (
      <ul className="divide-y divide-slate-100">
        {reminders.data.map((reminder) => {
          const type = PET_EVENT_TYPE_LABELS[reminder.type];
          return (
            <li key={reminder.event_id} className="flex flex-wrap items-center gap-3 py-3">
              <div className="min-w-0 flex-1">
                <p className="font-medium break-words text-slate-900">
                  <Link to={`/pets/${reminder.pet_id}`} className="underline-offset-2 hover:underline">
                    {reminder.pet_name}
                  </Link>
                </p>
                <p className="text-sm text-slate-700">
                  {type}
                  {reminder.description && ` · ${reminder.description}`}
                </p>
                <p
                  className={cn(
                    "mt-1 flex flex-wrap items-center gap-2 text-sm",
                    reminder.overdue ? "font-medium text-red-800" : "text-slate-700",
                  )}
                >
                  <span className="inline-flex items-center gap-1">
                    <CalendarDays aria-hidden="true" className="size-4" />
                    <span className="sr-only">Próxima data:</span>
                    {formatDate(reminder.next_due_on)}
                  </span>
                  {reminder.overdue && <Badge tone="danger">atrasado</Badge>}
                </p>
              </div>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => onRegister(reminder)}
                aria-label={`Registrar agora: ${type}${reminder.description ? ` ${reminder.description}` : ""} de ${reminder.pet_name}`}
              >
                Registrar agora
              </Button>
            </li>
          );
        })}
      </ul>
    );
  }

  return (
    <div className="space-y-4">
      <SelectField
        label="Período"
        options={WINDOW_OPTIONS}
        value={String(within)}
        onChange={(event) =>
          url.update({ within: event.target.value === String(DEFAULT_REMINDER_WINDOW) ? null : event.target.value })
        }
        className="max-w-xs"
      />
      {content}
    </div>
  );
}
