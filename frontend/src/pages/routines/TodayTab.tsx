import { CalendarCheck } from "lucide-react";
import { errorMessage } from "@/api/errors";
import type { Routine, RoutineToday } from "@/api/types";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { ProgressBar } from "@/components/ProgressBar";
import { SkeletonList } from "@/components/Spinner";
import { useLogRoutineDone, useUndoRoutineDone } from "@/hooks/useRoutineLog";
import { cn } from "@/lib/cn";
import { useRoutinesToday } from "./queries";
import { describeSchedule } from "./schedule";

/** Routines due today (server's date), each with a checkbox: check logs it, uncheck undoes it. */
export function TodayTab({ onOpen }: { onOpen: (routine: Routine) => void }) {
  const today = useRoutinesToday();
  const logDone = useLogRoutineDone();
  const undo = useUndoRoutineDone();

  if (today.isPending) return <SkeletonList rows={3} label="Carregando as rotinas de hoje..." />;
  if (today.isError) {
    return (
      <ErrorState
        title="Não foi possível carregar as rotinas de hoje"
        message={errorMessage(today.error)}
        onRetry={() => void today.refetch()}
      />
    );
  }
  if (today.data.length === 0) {
    return (
      <EmptyState
        icon={CalendarCheck}
        title="Nenhuma rotina prevista para hoje."
        description="Veja e crie rotinas na aba Todas."
      />
    );
  }

  const done = today.data.filter((routine) => routine.done_today).length;
  const score = `${done} de ${today.data.length} feitas`;
  const toggle = (routine: RoutineToday) => (routine.done_today ? undo.mutate(routine) : logDone.mutate(routine));

  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        <p aria-live="polite" className="text-sm font-medium text-slate-800">
          {score}
        </p>
        <ProgressBar value={done} max={today.data.length} label="Rotinas feitas hoje" valueText={score} />
      </div>
      <ul className="divide-y divide-slate-100">
        {today.data.map((routine) => (
          <li key={routine.id} className="flex items-center gap-3 py-2">
            <input
              type="checkbox"
              checked={routine.done_today}
              onChange={() => toggle(routine)}
              aria-label={`Feita hoje: ${routine.name}`}
              className="size-5 shrink-0 accent-brand-700"
            />
            <div className="min-w-0 flex-1">
              <button
                type="button"
                onClick={() => onOpen(routine)}
                className={cn(
                  "max-w-full text-left font-medium break-words underline-offset-2 hover:underline",
                  routine.done_today ? "text-slate-600 line-through" : "text-slate-900",
                )}
              >
                {routine.name}
              </button>
              <p className="text-sm text-slate-700">{describeSchedule(routine)}</p>
            </div>
            {routine.time_of_day && (
              <span className="shrink-0 text-sm text-slate-700">{routine.time_of_day.slice(0, 5)}</span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
