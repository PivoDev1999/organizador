import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { dashboardKeys } from "@/api/dashboard";
import { errorMessage } from "@/api/errors";
import { replaceInPage } from "@/api/pagination";
import { createTask, deleteTask, listTasks, taskKeys, updateTask, type TaskFilters } from "@/api/tasks";
import type { Page, Task, TaskCreate, TaskStatus, TaskUpdate } from "@/api/types";
import { useToast } from "@/components/toast/useToast";
import { isNotFound } from "@/lib/formErrors";

export function useTasks(filters: TaskFilters, pages: number) {
  return useQuery({
    queryKey: taskKeys.list(filters, pages),
    queryFn: () => listTasks(filters, pages),
    // "Carregar mais" and filter changes keep the current list on screen while the next one loads.
    placeholderData: keepPreviousData,
  });
}

/** Tasks feed the dashboard (overdue, due today, doing): refresh both after a change. */
function useRefreshTasks() {
  const queryClient = useQueryClient();
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: taskKeys.all }),
      queryClient.invalidateQueries({ queryKey: dashboardKeys.all }),
    ]);
}

const SET_DONE_MUTATION_KEY = ["tasks", "set-done"] as const;

export interface SetDoneVariables {
  task: Task;
  done: boolean;
}

/**
 * Checkbox "concluída": PATCH status=done, or back to todo. Optimistic in every cached list; on
 * failure only that task goes back to its previous status (others changed meanwhile stay) and the
 * error goes to a toast. Lists and dashboard are fetched again when the last of these settles.
 */
export function useSetTaskDone() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const refresh = useRefreshTasks();
  const mutationKey = SET_DONE_MUTATION_KEY;

  const setStatus = (id: string, status: TaskStatus) =>
    queryClient.setQueriesData<Page<Task>>({ queryKey: taskKeys.lists() }, (page) =>
      replaceInPage(page, id, (task) => ({ ...task, status })),
    );

  return useMutation({
    mutationKey,
    mutationFn: ({ task, done }: SetDoneVariables) => updateTask(task.id, { status: done ? "done" : "todo" }),
    onMutate: async ({ task, done }) => {
      await queryClient.cancelQueries({ queryKey: taskKeys.lists() });
      setStatus(task.id, done ? "done" : "todo");
    },
    onError: (error, { task }) => {
      setStatus(task.id, task.status);
      toast.error(errorMessage(error));
    },
    onSettled: () => {
      if (queryClient.isMutating({ mutationKey }) === 1) return refresh();
    },
  });
}

export function useSaveTask(task: Task | null) {
  const refresh = useRefreshTasks();
  return useMutation({
    mutationFn: (body: TaskCreate & TaskUpdate) => (task ? updateTask(task.id, body) : createTask(body)),
    onSuccess: () => refresh(),
    // Deleted on another device: the form closes and the list drops it.
    onError: (error) => (isNotFound(error) ? refresh() : undefined),
  });
}

export function useDeleteTask() {
  const refresh = useRefreshTasks();
  const toast = useToast();
  return useMutation({
    mutationFn: (task: Task) => deleteTask(task.id),
    onSuccess: () => toast.success("Tarefa excluída."),
    onError: (error) => toast.error(errorMessage(error)),
    onSettled: () => refresh(),
  });
}
