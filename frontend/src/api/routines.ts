import { apiFetch } from "./client";
import { ApiError } from "./errors";

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
