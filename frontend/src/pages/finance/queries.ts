import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { dashboardKeys } from "@/api/dashboard";
import { ApiError, errorMessage } from "@/api/errors";
import {
  copyBudgets,
  createBudget,
  createTransaction,
  deleteBudget,
  deleteTransaction,
  financeKeys,
  listTransactionCategories,
  listTransactions,
  payTransaction,
  unpayTransaction,
  updateBudget,
  updateTransaction,
  type TransactionFilters,
} from "@/api/finance";
import type { Budget, BudgetCopy, Transaction, TransactionCreate, TransactionUpdate } from "@/api/types";
import { useToast } from "@/components/toast/useToast";
import { isNotFound } from "@/lib/formErrors";

export function useTransactions(filters: TransactionFilters, pages: number) {
  return useQuery({
    queryKey: financeKeys.transactionList(filters, pages),
    queryFn: () => listTransactions(filters, pages),
    placeholderData: keepPreviousData,
  });
}

export function useTransactionCategories() {
  return useQuery({ queryKey: financeKeys.categories(), queryFn: listTransactionCategories });
}

/**
 * Any finance change can move a list, a month's summary and the budgets' `spent` (a due date may
 * change months too), and the dashboard shows bills, the month and budget alerts: refresh them all.
 */
export function useRefreshFinance() {
  const queryClient = useQueryClient();
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: financeKeys.transactions }),
      queryClient.invalidateQueries({ queryKey: financeKeys.budgetsAll }),
      queryClient.invalidateQueries({ queryKey: dashboardKeys.all }),
    ]);
}

/** 404 (deleted elsewhere) and 409 (already paid / not paid) mean the list is stale. */
function isStale(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 404 || error.status === 409);
}

export function useSaveTransaction(transaction: Transaction | null) {
  const refresh = useRefreshFinance();
  return useMutation({
    // The PATCH refuses `paid_on` (payment goes through /pay): the form only sends it when creating.
    mutationFn: (body: TransactionCreate & TransactionUpdate) =>
      transaction ? updateTransaction(transaction.id, body) : createTransaction(body),
    onSuccess: () => refresh(),
    onError: (error) => (isNotFound(error) ? refresh() : undefined),
  });
}

export function useDeleteTransaction() {
  const refresh = useRefreshFinance();
  const toast = useToast();
  return useMutation({
    mutationFn: (transaction: Transaction) => deleteTransaction(transaction.id),
    onSuccess: () => toast.success("Transação excluída."),
    onError: (error) => toast.error(errorMessage(error)),
    onSettled: () => refresh(),
  });
}

export function usePayTransaction() {
  const refresh = useRefreshFinance();
  return useMutation({
    mutationFn: ({ transaction, paidOn }: { transaction: Transaction; paidOn: string }) =>
      payTransaction(transaction.id, paidOn),
    onSuccess: () => refresh(),
    onError: (error) => (isStale(error) ? refresh() : undefined),
  });
}

export function useUnpayTransaction() {
  const refresh = useRefreshFinance();
  const toast = useToast();
  return useMutation({
    mutationFn: (transaction: Transaction) => unpayTransaction(transaction.id),
    onSuccess: () => toast.success("Pagamento desfeito."),
    onError: (error) => toast.error(errorMessage(error)),
    onSettled: () => refresh(),
  });
}

export interface BudgetVariables {
  category: string;
  amount: string;
}

/** Create (category, amount, month) or change the amount of an existing budget. */
export function useSaveBudget(budget: Budget | null, month: string) {
  const refresh = useRefreshFinance();
  return useMutation({
    mutationFn: ({ category, amount }: BudgetVariables) =>
      budget ? updateBudget(budget.id, { amount }) : createBudget({ category, amount, month }),
    onSuccess: () => refresh(),
    onError: (error) => (isStale(error) ? refresh() : undefined),
  });
}

export function useDeleteBudget() {
  const refresh = useRefreshFinance();
  const toast = useToast();
  return useMutation({
    mutationFn: (budget: Budget) => deleteBudget(budget.id),
    onSuccess: () => toast.success("Orçamento excluído."),
    onError: (error) => toast.error(errorMessage(error)),
    onSettled: () => refresh(),
  });
}

function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}

/** Toast text of "Copiar do mês anterior", naming the skipped categories. */
export function copyMessage({ created, skipped }: BudgetCopy): string {
  const list = skipped.join(", ");
  if (created.length === 0) {
    return skipped.length > 0 ? `Nada a copiar: as categorias já tinham orçamento (${list}).` : "Nada a copiar.";
  }
  const copied = plural(created.length, "orçamento copiado", "orçamentos copiados");
  if (skipped.length === 0) return `${copied}.`;
  return `${copied} (${skipped.length} já ${skipped.length === 1 ? "existia" : "existiam"}: ${list}).`;
}

export function useCopyBudgets() {
  const refresh = useRefreshFinance();
  const toast = useToast();
  return useMutation({
    mutationFn: ({ from, to }: { from: string; to: string }) => copyBudgets(from, to),
    onSuccess: (result) => {
      if (result.created.length === 0) toast.info(copyMessage(result));
      else toast.success(copyMessage(result));
    },
    onError: (error) => toast.error(errorMessage(error)),
    onSettled: () => refresh(),
  });
}
