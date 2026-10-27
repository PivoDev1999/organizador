import { apiFetch } from "./client";
import { fetchFirstPages } from "./pagination";
import type { Page, QueryParams, Task, TaskCreate, TaskUpdate } from "./types";

/** Filters of GET /api/tasks, without pagination (the screen asks for pages). */
export type TaskFilters = Omit<NonNullable<QueryParams<"/api/tasks", "get">>, "limit" | "offset">;

export const taskKeys = {
  all: ["tasks"] as const,
  lists: () => ["tasks", "list"] as const,
  list: (filters: TaskFilters, pages: number) => ["tasks", "list", filters, pages] as const,
};

export function listTasks(filters: TaskFilters, pages: number): Promise<Page<Task>> {
  return fetchFirstPages(
    (limit, offset) => apiFetch("/api/tasks", { query: { ...filters, limit, offset } }),
    pages,
  );
}

export function createTask(body: TaskCreate): Promise<Task> {
  return apiFetch("/api/tasks", { method: "post", json: body });
}

export function updateTask(id: string, body: TaskUpdate): Promise<Task> {
  return apiFetch("/api/tasks/{task_id}", { method: "patch", params: { task_id: id }, json: body });
}

export function deleteTask(id: string): Promise<undefined> {
  return apiFetch("/api/tasks/{task_id}", { method: "delete", params: { task_id: id } });
}
