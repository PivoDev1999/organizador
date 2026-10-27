import { apiFetch } from "./client";
import { fetchFirstPages } from "./pagination";
import type { Page, PantryAlerts, PantryItem, PantryItemCreate, PantryItemUpdate, QueryParams } from "./types";

/** Filters of GET /api/pantry, without pagination (the screen asks for pages). */
export type PantryFilters = Omit<NonNullable<QueryParams<"/api/pantry", "get">>, "limit" | "offset">;

/** Window of "vence em breve" of the alerts card, in days (same as the dashboard). */
export const ALERTS_EXPIRING_WITHIN = 7;

export const pantryKeys = {
  all: ["pantry"] as const,
  lists: () => ["pantry", "list"] as const,
  list: (filters: PantryFilters, pages: number) => ["pantry", "list", filters, pages] as const,
  /** Items for a select (e.g. the shopping form), optionally searched by name. */
  allOptions: () => ["pantry", "options"] as const,
  options: (q: string) => ["pantry", "options", q] as const,
  alerts: () => ["pantry", "alerts"] as const,
  categories: () => ["pantry", "categories"] as const,
  locations: () => ["pantry", "locations"] as const,
};

export function listPantryItems(filters: PantryFilters, pages: number): Promise<Page<PantryItem>> {
  return fetchFirstPages(
    (limit, offset) => apiFetch("/api/pantry", { query: { ...filters, limit, offset } }),
    pages,
  );
}

/** Up to 100 items by name, for pickers; `q` narrows down long lists. */
export function listPantryOptions(q: string): Promise<Page<PantryItem>> {
  return apiFetch("/api/pantry", { query: { q: q || undefined, sort: "name", limit: 100 } });
}

export function getPantryAlerts(): Promise<PantryAlerts> {
  return apiFetch("/api/pantry/alerts", { query: { expiring_within: ALERTS_EXPIRING_WITHIN } });
}

export function listPantryCategories(): Promise<string[]> {
  return apiFetch("/api/pantry/categories");
}

export function listPantryLocations(): Promise<string[]> {
  return apiFetch("/api/pantry/locations");
}

export function createPantryItem(body: PantryItemCreate): Promise<PantryItem> {
  return apiFetch("/api/pantry", { method: "post", json: body });
}

export function updatePantryItem(id: string, body: PantryItemUpdate): Promise<PantryItem> {
  return apiFetch("/api/pantry/{item_id}", { method: "patch", params: { item_id: id }, json: body });
}

export function deletePantryItem(id: string): Promise<undefined> {
  return apiFetch("/api/pantry/{item_id}", { method: "delete", params: { item_id: id } });
}

export type StockAction = "consume" | "restock";

/** Consumes or restocks `amount` (decimal string with a dot). Consuming more than there is: 409. */
export function changeStock(id: string, action: StockAction, amount: string): Promise<PantryItem> {
  const path = action === "consume" ? "/api/pantry/{item_id}/consume" : "/api/pantry/{item_id}/restock";
  return apiFetch(path, { method: "post", params: { item_id: id }, json: { amount } });
}
