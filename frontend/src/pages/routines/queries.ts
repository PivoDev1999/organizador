import { keepPreviousData, useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { dashboardKeys } from "@/api/dashboard";
import { errorMessage } from "@/api/errors";
import { PAGE_SIZE } from "@/api/pagination";
import {
  createRoutine,
  deleteRoutine,
  listRoutineLogs,
  listRoutines,
  listRoutinesToday,
  routineKeys,
  updateRoutine,
  type RoutineFilters,
} from "@/api/routines";
import type { Routine, RoutineCreate, RoutineUpdate } from "@/api/types";
import { useToast } from "@/components/toast/useToast";
import { isNotFound } from "@/lib/formErrors";

export function useRoutinesToday() {
  return useQuery({ queryKey: routineKeys.today(), queryFn: listRoutinesToday, refetchOnWindowFocus: true });
}

export function useRoutines(filters: RoutineFilters, pages: number) {
  return useQuery({
    queryKey: routineKeys.list(filters, pages),
    queryFn: () => listRoutines(filters, pages),
    placeholderData: keepPreviousData,
  });
}

/** History of one routine, newest first, a page at a time (kept in the dialog, not in the URL). */
export function useRoutineLogs(routineId: string) {
  return useInfiniteQuery({
    queryKey: routineKeys.logs(routineId),
    queryFn: ({ pageParam }) => listRoutineLogs(routineId, pageParam),
    initialPageParam: 0,
    getNextPageParam: (last) => {
      const next = last.offset + PAGE_SIZE;
      return next < last.total ? next : undefined;
    },
  });
}

/** Routines feed the dashboard ("Rotina de hoje"): refresh both after a change. */
function useRefreshRoutines() {
  const queryClient = useQueryClient();
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: routineKeys.all }),
      queryClient.invalidateQueries({ queryKey: dashboardKeys.all }),
    ]);
}

export function useSaveRoutine(routine: Routine | null) {
  const refresh = useRefreshRoutines();
  return useMutation({
    mutationFn: (body: RoutineCreate & RoutineUpdate) =>
      routine ? updateRoutine(routine.id, body) : createRoutine(body),
    onSuccess: () => refresh(),
    // Deleted on another device: the form closes and the list drops it.
    onError: (error) => (isNotFound(error) ? refresh() : undefined),
  });
}

export function useDeleteRoutine() {
  const refresh = useRefreshRoutines();
  const toast = useToast();
  return useMutation({
    mutationFn: (routine: Routine) => deleteRoutine(routine.id),
    onSuccess: () => toast.success("Rotina excluída."),
    onError: (error) => toast.error(errorMessage(error)),
    onSettled: () => refresh(),
  });
}
