import { useMutation, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { dashboardKeys } from "@/api/dashboard";
import { errorMessage } from "@/api/errors";
import { logRoutineDone, routineKeys, undoRoutineToday } from "@/api/routines";
import type { Dashboard, RoutineToday } from "@/api/types";
import { useToast } from "@/components/toast/useToast";

function setRoutineDone(dashboard: Dashboard, routineId: string, done: boolean): Dashboard {
  const target = dashboard.routines.due_today.find((routine) => routine.id === routineId);
  if (!target || target.done_today === done) return dashboard;
  return {
    ...dashboard,
    routines: {
      ...dashboard.routines,
      due_today: dashboard.routines.due_today.map((routine) =>
        routine.id === routineId ? { ...routine, done_today: done } : routine,
      ),
      done: dashboard.routines.done + (done ? 1 : -1),
    },
  };
}

/** The dashboard with the routine marked as done (score + 1); unchanged if it already was. */
export function withRoutineDone(dashboard: Dashboard, routineId: string): Dashboard {
  return setRoutineDone(dashboard, routineId, true);
}

/** Undoes `withRoutineDone` for one routine only (score - 1), keeping the other changes in flight. */
export function withRoutineUndone(dashboard: Dashboard, routineId: string): Dashboard {
  return setRoutineDone(dashboard, routineId, false);
}

/**
 * Shared by marking and unmarking, on the dashboard and on the routines page: the caches are only
 * fetched again when the last of these mutations settles (an earlier refetch would bring back the
 * old state of a routine whose request is still in flight).
 */
export const ROUTINE_LOG_MUTATION_KEY = ["routines", "log"] as const;

/** Changes one routine in every cache that shows "today" (dashboard and /routines/today). */
function patchToday(queryClient: QueryClient, routineId: string, done: boolean) {
  queryClient.setQueriesData<Dashboard>({ queryKey: dashboardKeys.all }, (current) =>
    current && setRoutineDone(current, routineId, done),
  );
  queryClient.setQueryData<RoutineToday[]>(routineKeys.today(), (current) =>
    current?.map((routine) => (routine.id === routineId ? { ...routine, done_today: done } : routine)),
  );
}

function useTodayMutation(mutationFn: (routine: RoutineToday) => Promise<unknown>, done: boolean) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const mutationKey = ROUTINE_LOG_MUTATION_KEY;

  return useMutation({
    mutationKey,
    mutationFn,
    onMutate: async (routine) => {
      await Promise.all([
        queryClient.cancelQueries({ queryKey: dashboardKeys.all }),
        queryClient.cancelQueries({ queryKey: routineKeys.today() }),
      ]);
      patchToday(queryClient, routine.id, done);
    },
    // Rolls back only this routine: others changed meanwhile stay as they are. "Already done" (409)
    // and "already undone" resolve as success, so they never get here and keep the change.
    onError: (error, routine) => {
      patchToday(queryClient, routine.id, !done);
      toast.error(errorMessage(error));
    },
    // This mutation still counts as running here, so 1 means "no other one in flight".
    onSettled: () => {
      if (queryClient.isMutating({ mutationKey }) === 1) {
        return Promise.all([
          queryClient.invalidateQueries({ queryKey: dashboardKeys.all }),
          queryClient.invalidateQueries({ queryKey: routineKeys.all }),
        ]);
      }
    },
  });
}

/**
 * Marks a routine of today as done. Optimistic: the checkbox and the dashboard score change at once;
 * on failure only that routine rolls back and the error goes to a toast. A 409 ("already done", e.g.
 * from another device) keeps the change.
 */
export function useLogRoutineDone() {
  return useTodayMutation((routine) => logRoutineDone(routine.id), true);
}

/** Undoes today's mark of a routine, with the same optimistic update and rollback. */
export function useUndoRoutineDone() {
  return useTodayMutation((routine) => undoRoutineToday(routine.id), false);
}
