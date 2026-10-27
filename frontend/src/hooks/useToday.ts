import { localToday } from "@/lib/today";

/**
 * Today as "YYYY-MM-DD" for rules computed on the client (e.g. the "atrasada" badge of tasks).
 *
 * Always the device's local date: the system runs on the home network, where the server and the
 * devices share the same time zone. A cached server date (e.g. the dashboard's) is not used because
 * it can still hold yesterday right after midnight. Where it matters, the API stays the source of
 * truth: the "Atrasadas" filter sends `overdue=true` and the server decides with its own today.
 */
export function useToday(): string {
  return localToday();
}
