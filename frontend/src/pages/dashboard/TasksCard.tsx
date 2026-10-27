import { CalendarClock, CircleDashed, ListTodo, TriangleAlert } from "lucide-react";
import type { Dashboard, Task } from "@/api/types";
import { PreviewList } from "@/components/PreviewList";
import { SectionCard } from "@/components/SectionCard";
import { StatBadge } from "@/components/StatBadge";
import { formatDate } from "@/lib/format";

function TaskRow({ task, overdue }: { task: Task; overdue: boolean }) {
  return (
    <div className="flex items-start justify-between gap-2">
      <span className="min-w-0 break-words text-slate-900">{task.title}</span>
      {overdue && <span className="shrink-0 text-sm text-red-800">{formatDate(task.due_date)}</span>}
    </div>
  );
}

export function TasksCard({ tasks }: { tasks: Dashboard["tasks"] }) {
  const { overdue, due_today: dueToday, doing_total: doing } = tasks;
  const nothingDue = overdue.total === 0 && dueToday.total === 0;

  return (
    <SectionCard title="Afazeres" icon={ListTodo} to="/tarefas">
      <div className="mb-3 flex flex-wrap gap-2">
        <StatBadge value={doing} label="em andamento" tone="info" icon={CircleDashed} />
      </div>
      {nothingDue && <p className="text-slate-700">Nenhuma tarefa atrasada ou para hoje.</p>}
      {overdue.total > 0 && (
        <div className="mb-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2">
          <h3 className="flex items-center gap-1.5 font-semibold text-red-800">
            <TriangleAlert aria-hidden="true" className="size-4" />
            Atrasadas ({overdue.total})
          </h3>
          <PreviewList
            items={overdue.items}
            total={overdue.total}
            getKey={(task) => task.id}
            renderItem={(task) => <TaskRow task={task} overdue />}
            moreLabel={(n) => `e mais ${n} atrasadas`}
          />
        </div>
      )}
      {dueToday.total > 0 && (
        <div>
          <h3 className="flex items-center gap-1.5 font-semibold text-slate-800">
            <CalendarClock aria-hidden="true" className="size-4" />
            Vencem hoje ({dueToday.total})
          </h3>
          <PreviewList
            items={dueToday.items}
            total={dueToday.total}
            getKey={(task) => task.id}
            renderItem={(task) => <TaskRow task={task} overdue={false} />}
            moreLabel={(n) => `e mais ${n} para hoje`}
          />
        </div>
      )}
    </SectionCard>
  );
}
