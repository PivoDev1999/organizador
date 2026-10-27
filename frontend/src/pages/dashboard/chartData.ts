// Turns API data into chart rows. Money stays a decimal string for every text (labels, tooltip,
// screen reader table); `value` is a float used only to size the bars.
import type { Budget, CategoryTotals } from "@/api/types";
import { budgetLevel, compareDecimal, sumDecimals, type BudgetLevel } from "@/lib/decimal";
import { formatMoney, formatPercent } from "@/lib/format";

export const MAX_CATEGORIES = 6;
export const OTHER_CATEGORIES = "Outras";

export interface CategoryDatum {
  category: string;
  /** Exact total from the API ("123.45"). */
  total: string;
  /** formatMoney(total), for labels and tooltip. */
  label: string;
  /** Bar length only. */
  value: number;
}

function categoryDatum(category: string, total: string): CategoryDatum {
  return { category, total, label: formatMoney(total), value: Number(total) };
}

/**
 * Expenses of the month by category, largest first (exact comparison; ties by name). Beyond `max`
 * categories, the rest is summed into a single "Outras" row at the end.
 */
export function prepareCategoryData(byCategory: readonly CategoryTotals[], max = MAX_CATEGORIES): CategoryDatum[] {
  const expenses = byCategory
    .filter((item) => item.type === "expense" && compareDecimal(item.total, "0") > 0)
    .sort((a, b) => compareDecimal(b.total, a.total) || a.category.localeCompare(b.category, "pt-BR"));
  if (expenses.length <= max) return expenses.map((item) => categoryDatum(item.category, item.total));
  const top = expenses.slice(0, max).map((item) => categoryDatum(item.category, item.total));
  const rest = sumDecimals(expenses.slice(max).map((item) => item.total));
  return [...top, categoryDatum(OTHER_CATEGORIES, rest)];
}

export interface BudgetDatum {
  id: string;
  category: string;
  spent: string;
  amount: string;
  level: BudgetLevel;
  /** "85,5%", or a note for a zero budget (no percentage exists). */
  label: string;
  /** Bar length in percent. A zero budget with spending is drawn full (it is exceeded). */
  value: number;
}

export function prepareBudgetData(budgets: readonly Budget[]): BudgetDatum[] {
  return budgets.map((budget) => {
    const level = budgetLevel(budget.spent, budget.amount);
    const zeroBudget = budget.percent_used === null;
    return {
      id: budget.id,
      category: budget.category,
      spent: budget.spent,
      amount: budget.amount,
      level,
      label: zeroBudget ? (level === "exceeded" ? "sem orçamento" : "0%") : formatPercent(budget.percent_used),
      value: zeroBudget ? (level === "exceeded" ? 100 : 0) : Number(budget.percent_used),
    };
  });
}

export const BUDGET_LEVEL_LABELS: Record<BudgetLevel, string> = {
  normal: "dentro do orçamento",
  warning: "atenção",
  exceeded: "estourado",
};
