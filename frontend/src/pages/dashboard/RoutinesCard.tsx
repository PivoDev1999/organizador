import { Repeat } from "lucide-react";
import type { Dashboard, RoutineToday } from "@/api/types";
import { ProgressBar } from "@/components/ProgressBar";
import { SectionCard } from "@/components/SectionCard";
import { cn } from "@/lib/cn";
import { useLogRoutineDone } from "@/hooks/useRoutineLog";

function RoutineRow({ routine, onDone }: { routine: RoutineToday; onDone: (routine: RoutineToday) => void }) {
  const done = routine.done_today;
  return (
    <label
      className={cn(
        "flex min-h-11 items-center gap-3 rounded-lg px-2",
        done ? "cursor-default" : "cursor-pointer hover:bg-slate-50",
      )}
    >
      <input
        type="checkbox"
        checked={done}
        disabled={done}
        onChange={() => onDone(routine)}
        className="size-5 shrink-0 accent-brand-700"
      />
      <span className={cn("min-w-0 flex-1 break-words", done ? "text-slate-600 line-through" : "text-slate-900")}>
        {routine.name}
      </span>
      {routine.time_of_day && <span className="shrink-0 text-sm text-slate-700">{routine.time_of_day.slice(0, 5)}</span>}
    </label>
  );
}

export function RoutinesCard({ routines }: { routines: Dashboard["routines"] }) {
  const logDone = useLogRoutineDone();
  const { due_today: dueToday, done, total } = routines;
  const score = `${done} de ${total} feitas`;

  return (
    <SectionCard title="Rotina de hoje" icon={Repeat} to="/rotina">
      {total === 0 ? (
        <p className="text-slate-700">Nenhuma rotina prevista para hoje.</p>
      ) : (
        <>
          <div className="mb-3 space-y-1.5">
            {/* Polite live region: the new score is announced after a check. */}
            <p aria-live="polite" className="text-sm font-medium text-slate-800">
              {score}
            </p>
            <ProgressBar value={done} max={total} label="Rotinas feitas hoje" valueText={score} />
          </div>
          <ul className="space-y-1">
            {dueToday.map((routine) => (
              <li key={routine.id}>
                <RoutineRow routine={routine} onDone={(r) => logDone.mutate(r)} />
              </li>
            ))}
          </ul>
        </>
      )}
    </SectionCard>
  );
}
