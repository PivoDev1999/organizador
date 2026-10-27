import { CalendarDays, Pencil, Trash2 } from "lucide-react";
import type { Task } from "@/api/types";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { cn } from "@/lib/cn";
import { formatDate } from "@/lib/format";
import { TASK_PRIORITY_LABELS, TASK_PRIORITY_TONES } from "@/lib/labels";

/** Due before today and not done. Dates are "YYYY-MM-DD", so text order is date order. */
export function isTaskOverdue(task: Task, today: string): boolean {
  return task.due_date !== null && task.due_date < today && task.status !== "done";
}

export interface TaskRowProps {
  task: Task;
  today: string;
  onToggleDone: (task: Task, done: boolean) => void;
  onEdit: (task: Task) => void;
  onDelete: (task: Task) => void;
}

export function TaskRow({ task, today, onToggleDone, onEdit, onDelete }: TaskRowProps) {
  const done = task.status === "done";
  const overdue = isTaskOverdue(task, today);
  return (
    <div className="flex items-start gap-3 py-3">
      <input
        type="checkbox"
        checked={done}
        onChange={(event) => onToggleDone(task, event.target.checked)}
        aria-label={`Concluída: ${task.title}`}
        className="mt-1 size-5 shrink-0 accent-brand-700"
      />
      <div className="min-w-0 flex-1">
        <button
          type="button"
          onClick={() => onEdit(task)}
          className={cn(
            "max-w-full text-left font-medium break-words underline-offset-2 hover:underline",
            done ? "text-slate-600 line-through" : "text-slate-900",
          )}
        >
          {task.title}
        </button>
        <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-slate-700">
          <Badge tone={TASK_PRIORITY_TONES[task.priority]}>Prioridade {TASK_PRIORITY_LABELS[task.priority].toLowerCase()}</Badge>
          {task.status === "doing" && <Badge tone="info">em andamento</Badge>}
          {task.due_date && (
            <span className={cn("inline-flex items-center gap-1", overdue && "font-medium text-red-800")}>
              <CalendarDays aria-hidden="true" className="size-4" />
              <span className="sr-only">Prazo:</span>
              {formatDate(task.due_date)}
            </span>
          )}
          {overdue && <Badge tone="danger">atrasada</Badge>}
        </div>
      </div>
      <div className="flex shrink-0 gap-1">
        <Button variant="ghost" size="sm" onClick={() => onEdit(task)} aria-label={`Editar ${task.title}`}>
          <Pencil aria-hidden="true" className="size-4" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onDelete(task)}
          aria-label={`Excluir ${task.title}`}
          className="text-red-700 hover:bg-red-50"
        >
          <Trash2 aria-hidden="true" className="size-4" />
        </Button>
      </div>
    </div>
  );
}
