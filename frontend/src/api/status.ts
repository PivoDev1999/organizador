import { apiFetch } from "./client";
import type { SystemStatus } from "./types";

export const statusKeys = {
  all: ["status"] as const,
};

/** Version, uptime and the state of the database, file storage and last backup (requires login). */
export function getSystemStatus(): Promise<SystemStatus> {
  return apiFetch("/api/status");
}
