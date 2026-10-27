import { ListTodo, Plus } from "lucide-react";
import { useState } from "react";
import { errorMessage } from "@/api/errors";
import type { TaskFilters } from "@/api/tasks";
import type { Task, TaskPriority, TaskSort, TaskStatus } from "@/api/types";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { FilterChips, ToggleChip } from "@/components/FilterChips";
import { LoadMore } from "@/components/LoadMore";
import { PageHeader } from "@/components/PageHeader";
import { SearchField } from "@/components/SearchField";
import { SelectField } from "@/components/SelectField";
import { SkeletonList } from "@/components/Spinner";
import { useToday } from "@/hooks/useToday";
import { useUrlFilters } from "@/hooks/useUrlFilters";
import { labelOptions, TASK_PRIORITY_LABELS, TASK_SORT_LABELS, TASK_STATUS_LABELS } from "@/lib/labels";
import { useDeleteTask, useSetTaskDone, useTasks } from "./tasks/queries";
import { TaskFormModal } from "./tasks/TaskFormModal";
import { TaskRow } from "./tasks/TaskRow";

const STATUSES = labelOptions(TASK_STATUS_LABELS);
const PRIORITIES = labelOptions(TASK_PRIORITY_LABELS);
const SORTS = labelOptions(TASK_SORT_LABELS);
const DEFAULT_SORT: TaskSort = "due_date";

/** null: closed; "new": creating; a task: editing. */
type Editing = Task | "new" | null;

export function TasksPage() {
  const url = useUrlFilters();
  const today = useToday();
  const filters: TaskFilters = {
    status: url.getEnumList<TaskStatus>("status", STATUSES.map((o) => o.value)),
    priority: url.getEnumList<TaskPriority>("priority", PRIORITIES.map((o) => o.value)),
    overdue: url.getFlag("overdue") || undefined,
    q: url.getText("q") || undefined,
    sort: url.getEnum<TaskSort>("sort", SORTS.map((o) => o.value), DEFAULT_SORT),
  };
  const tasks = useTasks(filters, url.pages);
  const setDone = useSetTaskDone();
  const remove = useDeleteTask();
  const [editing, setEditing] = useState<Editing>(null);
  const [deleting, setDeleting] = useState<Task | null>(null);
  const hasFilters = Boolean(filters.status?.length || filters.priority?.length || filters.overdue || filters.q);

  let content;
  if (tasks.isPending) {
    content = <SkeletonList rows={4} label="Carregando tarefas..." />;
  } else if (tasks.isError) {
    content = (
      <ErrorState
        title="Não foi possível carregar as tarefas"
        message={errorMessage(tasks.error)}
        onRetry={() => void tasks.refetch()}
      />
    );
  } else if (tasks.data.items.length === 0) {
    content = hasFilters ? (
      <EmptyState title="Nenhuma tarefa encontrada." description="Tente mudar ou limpar os filtros." />
    ) : (
      <EmptyState
        icon={ListTodo}
        title="Nenhuma tarefa ainda."
        description="Crie a primeira tarefa da casa."
        action={<Button onClick={() => setEditing("new")}>Nova tarefa</Button>}
      />
    );
  } else {
    content = (
      <>
        <ul className="divide-y divide-slate-100" aria-busy={tasks.isPlaceholderData}>
          {tasks.data.items.map((task) => (
            <li key={task.id}>
              <TaskRow
                task={task}
                today={today}
                onToggleDone={(t, done) => setDone.mutate({ task: t, done })}
                onEdit={setEditing}
                onDelete={setDeleting}
              />
            </li>
          ))}
        </ul>
        <LoadMore
          shown={tasks.data.items.length}
          total={tasks.data.total}
          loading={tasks.isPlaceholderData}
          onLoadMore={url.loadMore}
          canLoadMore={url.canLoadMore}
        />
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Tarefas"
        actions={
          <Button onClick={() => setEditing("new")}>
            <Plus aria-hidden="true" className="size-5" />
            Nova tarefa
          </Button>
        }
      />
      <div className="space-y-4">
        <Card>
          <div className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-[1fr_auto]">
              <SearchField
                label="Buscar"
                placeholder="Título ou descrição"
                value={filters.q ?? ""}
                onSearch={(q) => url.update({ q })}
              />
              <SelectField
                label="Ordenar por"
                options={SORTS}
                value={filters.sort}
                onChange={(event) => url.update({ sort: event.target.value === DEFAULT_SORT ? null : event.target.value })}
              />
            </div>
            <div className="flex flex-wrap gap-x-6 gap-y-3">
              <FilterChips
                label="Status"
                options={STATUSES}
                selected={filters.status ?? []}
                onChange={(status) => url.update({ status })}
              />
              <FilterChips
                label="Prioridade"
                options={PRIORITIES}
                selected={filters.priority ?? []}
                onChange={(priority) => url.update({ priority })}
              />
              <div className="space-y-1">
                <p className="text-sm font-medium text-slate-800">Prazo</p>
                <ToggleChip
                  label="Atrasadas"
                  pressed={Boolean(filters.overdue)}
                  onToggle={(overdue) => url.update({ overdue })}
                />
              </div>
            </div>
          </div>
        </Card>
        <Card title="Lista de tarefas">{content}</Card>
      </div>

      {editing && <TaskFormModal task={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
      {deleting && (
        <ConfirmDialog
          title="Excluir tarefa?"
          message={`"${deleting.title}" e os anexos dela serão excluídos.`}
          loading={remove.isPending}
          onConfirm={() => remove.mutate(deleting, { onSettled: () => setDeleting(null) })}
          onCancel={() => setDeleting(null)}
        />
      )}
    </>
  );
}
