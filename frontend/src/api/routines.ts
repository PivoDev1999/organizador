import { apiFetch } from "./client";
import { ApiError } from "./errors";
import { fetchFirstPages, PAGE_SIZE } from "./pagination";
import type { Page, QueryParams, Routine, RoutineCreate, RoutineLog, RoutineToday, RoutineUpdate } from "./types";

/** Filters of GET /api/routines, without pagination (the screen asks for pages). */
export type RoutineFilters = Omit<NonNullable<QueryParams<"/api/routines", "get">>, "limit" | "offset">;

export const routineKeys = {
  all: ["routines"] as const,
  today: () => ["routines", "today"] as const,
  lists: () => ["routines", "list"] as const,
  list: (filters: RoutineFilters, pages: number) => ["routines", "list", filters, pages] as const,
  logs: (routineId: string) => ["routines", "logs", routineId] as const,
};

export function listRoutinesToday(): Promise<RoutineToday[]> {
  return apiFetch("/api/routines/today");
}

export function listRoutines(filters: RoutineFilters, pages: number): Promise<Page<Routine>> {
  return fetchFirstPages(
    (limit, offset) => apiFetch("/api/routines", { query: { ...filters, limit, offset } }),
    pages,
  );
}

export function createRoutine(body: RoutineCreate): Promise<Routine> {
  return apiFetch("/api/routines", { method: "post", json: body });
}

export function updateRoutine(id: string, body: RoutineUpdate): Promise<Routine> {
  return apiFetch("/api/routines/{routine_id}", { method: "patch", params: { routine_id: id }, json: body });
}

export function deleteRoutine(id: string): Promise<undefined> {
  return apiFetch("/api/routines/{routine_id}", { method: "delete", params: { routine_id: id } });
}

/** One page of the history, most recent first. */
export function listRoutineLogs(routineId: string, offset: number): Promise<Page<RoutineLog>> {
  return apiFetch("/api/routines/{routine_id}/logs", {
    params: { routine_id: routineId },
    query: { limit: PAGE_SIZE, offset },
  });
}

export type LogDoneResult = "logged" | "already-done";

/**
 * Marks the routine as done today (empty body = today in the server's time zone). A 409 means it was
 * already marked (e.g. on another device): for the user that is the same outcome, not an error.
 */
export async function logRoutineDone(routineId: string): Promise<LogDoneResult> {
  try {
    await apiFetch("/api/routines/{routine_id}/logs", { method: "post", params: { routine_id: routineId } });
    return "logged";
  } catch (error) {
    if (error instanceof ApiError && error.status === 409) return "already-done";
    throw error;
  }
}

export type UndoResult = "undone" | "already-undone";

/**
 * Undoes today's mark. The screen may be stale (tab open since before midnight, or another device
 * already undid it), so the state is read again from /routines/today first:
 * - not done today (or no longer due today): nothing is deleted, and for the user that is the same
 *   outcome ("already undone"), like the 409 of `logRoutineDone`; the refetch fixes the screen;
 * - done today: the latest log is today's (the API rejects future dates), so its `done_on` is
 *   deleted. This uses the server's "today", never the device's clock or time zone.
 */
export async function undoRoutineToday(routineId: string): Promise<UndoResult> {
  const today = await listRoutinesToday();
  if (!today.some((routine) => routine.id === routineId && routine.done_today)) return "already-undone";
  const latest = await apiFetch("/api/routines/{routine_id}/logs", {
    params: { routine_id: routineId },
    query: { limit: 1 },
  });
  const log = latest.items[0];
  if (!log) return "already-undone";
  await apiFetch("/api/routines/{routine_id}/logs/{done_on}", {
    method: "delete",
    params: { routine_id: routineId, done_on: log.done_on },
  });
  return "undone";
}
