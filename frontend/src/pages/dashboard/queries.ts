import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { dashboardKeys, getDashboard, type DashboardParams } from "@/api/dashboard";
import { errorMessage } from "@/api/errors";
import { financeKeys, getMonthSummary, listBudgets } from "@/api/finance";
import { logRoutineDone } from "@/api/routines";
import type { Dashboard, RoutineToday } from "@/api/types";
import { useToast } from "@/components/toast/useToast";

/** One week ahead for expiries, reminders and bills; five items per list. */
export const DASHBOARD_PARAMS: DashboardParams = { within: 7, limit: 5 };

// The app turns refetch on focus off by default; a summary of "today" should catch up when the user
// comes back to the tab, so these queries turn it back on.
const LIVE = { refetchOnWindowFocus: true } as const;

export function useDashboard() {
  return useQuery({
    queryKey: dashboardKeys.detail(DASHBOARD_PARAMS),
    queryFn: () => getDashboard(DASHBOARD_PARAMS),
    ...LIVE,
  });
}

/** `month` comes from the dashboard's date (the server's today), so the queries wait for it. */
export function useMonthSummary(month: string | undefined) {
  return useQuery({
    queryKey: financeKeys.summary(month ?? ""),
    queryFn: () => getMonthSummary(month ?? ""),
    enabled: month !== undefined,
    ...LIVE,
  });
}

export function useBudgets(month: string | undefined) {
  return useQuery({
    queryKey: financeKeys.budgets(month ?? ""),
    queryFn: () => listBudgets(month ?? ""),
    enabled: month !== undefined,
    ...LIVE,
  });
}

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

const LOG_ROUTINE_MUTATION_KEY = ["routines", "log-done"] as const;

/**
 * Marks a routine of today as done. Optimistic: the checkbox and the score change at once. If the
 * request fails, only that routine is rolled back (others marked meanwhile stay) and the error goes to
 * a toast. A 409 ("already done", e.g. from another device) keeps the change. The dashboard is fetched
 * again when the last of these mutations settles: an earlier refetch would bring back, as pending, a
 * routine whose request is still in flight.
 */
export function useLogRoutineDone() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const queryKey = dashboardKeys.detail(DASHBOARD_PARAMS);
  const mutationKey = LOG_ROUTINE_MUTATION_KEY;

  return useMutation({
    mutationKey,
    mutationFn: (routine: RoutineToday) => logRoutineDone(routine.id),
    onMutate: async (routine) => {
      await queryClient.cancelQueries({ queryKey });
      queryClient.setQueryData<Dashboard>(queryKey, (current) => current && withRoutineDone(current, routine.id));
    },
    onError: (error, routine) => {
      queryClient.setQueryData<Dashboard>(queryKey, (current) => current && withRoutineUndone(current, routine.id));
      toast.error(errorMessage(error));
    },
    // This mutation still counts as running here, so 1 means "no other one in flight".
    onSettled: () => {
      if (queryClient.isMutating({ mutationKey }) === 1) {
        return queryClient.invalidateQueries({ queryKey: dashboardKeys.all });
      }
    },
  });
}
