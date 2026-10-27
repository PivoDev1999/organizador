import { apiFetch } from "./client";
import type { Budget, MonthSummary } from "./types";

/** `month` is "YYYY-MM". */
export const financeKeys = {
  summary: (month: string) => ["transactions", "summary", month] as const,
  budgets: (month: string) => ["budgets", month] as const,
};

export function getMonthSummary(month: string): Promise<MonthSummary> {
  return apiFetch("/api/transactions/summary", { query: { month } });
}

export function listBudgets(month: string): Promise<Budget[]> {
  return apiFetch("/api/budgets", { query: { month } });
}
