import { apiFetch } from "./client";
import type { Dashboard } from "./types";

export interface DashboardParams {
  /** Days ahead for pantry expiry, pet reminders and bills (overdue ones always come). */
  within: number;
  /** Max items per list; `total` still counts all of them. */
  limit: number;
}

export const dashboardKeys = {
  all: ["dashboard"] as const,
  detail: (params: DashboardParams) => ["dashboard", params] as const,
};

export function getDashboard(params: DashboardParams): Promise<Dashboard> {
  return apiFetch("/api/dashboard", { query: params });
}
