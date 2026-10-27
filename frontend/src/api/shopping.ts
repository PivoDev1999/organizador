import { apiFetch } from "./client";
import { fetchFirstPages } from "./pagination";
import type {
  Page,
  QueryParams,
  ShoppingItem,
  ShoppingItemCreate,
  ShoppingItemUpdate,
  ShoppingPurchase,
  ShoppingSummary,
} from "./types";

/** Filters of GET /api/shopping, without pagination (the screen asks for pages). */
export type ShoppingFilters = Omit<NonNullable<QueryParams<"/api/shopping", "get">>, "limit" | "offset">;

export const shoppingKeys = {
  all: ["shopping"] as const,
  lists: () => ["shopping", "list"] as const,
  list: (filters: ShoppingFilters, pages: number) => ["shopping", "list", filters, pages] as const,
  summary: () => ["shopping", "summary"] as const,
};

export function listShoppingItems(filters: ShoppingFilters, pages: number): Promise<Page<ShoppingItem>> {
  return fetchFirstPages(
    (limit, offset) => apiFetch("/api/shopping", { query: { ...filters, limit, offset } }),
    pages,
  );
}

export function getShoppingSummary(): Promise<ShoppingSummary> {
  return apiFetch("/api/shopping/summary");
}

export function createShoppingItem(body: ShoppingItemCreate): Promise<ShoppingItem> {
  return apiFetch("/api/shopping", { method: "post", json: body });
}

export function updateShoppingItem(id: string, body: ShoppingItemUpdate): Promise<ShoppingItem> {
  return apiFetch("/api/shopping/{item_id}", { method: "patch", params: { item_id: id }, json: body });
}

export function deleteShoppingItem(id: string): Promise<undefined> {
  return apiFetch("/api/shopping/{item_id}", { method: "delete", params: { item_id: id } });
}

/** Marks as bought; `pantry_restocked` tells whether the linked pantry item was restocked. */
export function purchaseShoppingItem(id: string): Promise<ShoppingPurchase> {
  return apiFetch("/api/shopping/{item_id}/purchase", { method: "post", params: { item_id: id } });
}

export function unpurchaseShoppingItem(id: string): Promise<ShoppingItem> {
  return apiFetch("/api/shopping/{item_id}/unpurchase", { method: "post", params: { item_id: id } });
}

/**
 * Adds the low stock pantry items to the list. The API answers 201 with the new items, or 200 with
 * `[]` when there is nothing to add (the OpenAPI schema declares that 200 without a body type, so the
 * response is checked here instead of trusting the generated type).
 */
export async function createFromPantry(includeExpired: boolean): Promise<ShoppingItem[]> {
  const created: unknown = await apiFetch("/api/shopping/from-pantry", {
    method: "post",
    query: { include_expired: includeExpired },
  });
  return Array.isArray(created) ? (created as ShoppingItem[]) : [];
}

export function deletePurchasedItems(): Promise<undefined> {
  return apiFetch("/api/shopping/purchased", { method: "delete" });
}
