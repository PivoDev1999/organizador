import { apiFetch } from "./client";
import { fetchFirstPages } from "./pagination";
import type {
  Budget,
  BudgetCopy,
  BudgetCreate,
  BudgetUpdate,
  MonthSummary,
  Page,
  QueryParams,
  Transaction,
  TransactionCreate,
  TransactionUpdate,
} from "./types";

/**
 * Filters of GET /api/transactions, without pagination. The screens filter by `month` only: the API
 * refuses `month` together with `due_from`/`due_to`.
 */
export type TransactionFilters = Omit<
  NonNullable<QueryParams<"/api/transactions", "get">>,
  "limit" | "offset" | "due_from" | "due_to"
>;

/** `month` is "YYYY-MM". */
export const financeKeys = {
  /** Lists, summaries and categories: any transaction change touches them. */
  transactions: ["transactions"] as const,
  transactionLists: () => ["transactions", "list"] as const,
  transactionList: (filters: TransactionFilters, pages: number) => ["transactions", "list", filters, pages] as const,
  categories: () => ["transactions", "categories"] as const,
  summary: (month: string) => ["transactions", "summary", month] as const,
  /** Budgets of every month (their `spent` follows the transactions). */
  budgetsAll: ["budgets"] as const,
  budgets: (month: string) => ["budgets", month] as const,
};

export function getMonthSummary(month: string): Promise<MonthSummary> {
  return apiFetch("/api/transactions/summary", { query: { month } });
}

export function listTransactions(filters: TransactionFilters, pages: number): Promise<Page<Transaction>> {
  return fetchFirstPages(
    (limit, offset) => apiFetch("/api/transactions", { query: { ...filters, limit, offset } }),
    pages,
  );
}

export function listTransactionCategories(): Promise<string[]> {
  return apiFetch("/api/transactions/categories");
}

/** `amount` goes as a decimal string ("12.90"): the API refuses floats for money. */
export function createTransaction(body: TransactionCreate): Promise<Transaction> {
  return apiFetch("/api/transactions", { method: "post", json: body });
}

export function updateTransaction(id: string, body: TransactionUpdate): Promise<Transaction> {
  return apiFetch("/api/transactions/{transaction_id}", {
    method: "patch",
    params: { transaction_id: id },
    json: body,
  });
}

export function deleteTransaction(id: string): Promise<undefined> {
  return apiFetch("/api/transactions/{transaction_id}", { method: "delete", params: { transaction_id: id } });
}

/** Already paid: 409. `paid_on` in the future or before 2000: 422. */
export function payTransaction(id: string, paidOn: string): Promise<Transaction> {
  return apiFetch("/api/transactions/{transaction_id}/pay", {
    method: "post",
    params: { transaction_id: id },
    json: { paid_on: paidOn },
  });
}

/** Not paid: 409. */
export function unpayTransaction(id: string): Promise<Transaction> {
  return apiFetch("/api/transactions/{transaction_id}/unpay", { method: "post", params: { transaction_id: id } });
}

export function listBudgets(month: string): Promise<Budget[]> {
  return apiFetch("/api/budgets", { query: { month } });
}

/** Category already budgeted in the month (case-insensitive): 409. */
export function createBudget(body: BudgetCreate): Promise<Budget> {
  return apiFetch("/api/budgets", { method: "post", json: body });
}

export function updateBudget(id: string, body: BudgetUpdate): Promise<Budget> {
  return apiFetch("/api/budgets/{budget_id}", { method: "patch", params: { budget_id: id }, json: body });
}

export function deleteBudget(id: string): Promise<undefined> {
  return apiFetch("/api/budgets/{budget_id}", { method: "delete", params: { budget_id: id } });
}

/**
 * Copies the budgets of `from` into `to`, skipping categories that already exist there. The API
 * answers 201 when it created any and 200 otherwise, both with `{created, skipped}`; the schema only
 * documents the 201 body, so the 200 one is typed here (and an empty answer counts as nothing copied).
 */
export async function copyBudgets(from: string, to: string): Promise<BudgetCopy> {
  const result = (await apiFetch("/api/budgets/copy", { method: "post", query: { from, to } })) as
    | BudgetCopy
    | undefined;
  return result ?? { created: [], skipped: [] };
}
