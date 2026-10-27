import { keepPreviousData, useMutation, useMutationState, useQuery, useQueryClient } from "@tanstack/react-query";
import { dashboardKeys } from "@/api/dashboard";
import { errorMessage } from "@/api/errors";
import { listPantryOptions, pantryKeys } from "@/api/pantry";
import {
  createFromPantry,
  createShoppingItem,
  deletePurchasedItems,
  deleteShoppingItem,
  getShoppingSummary,
  listShoppingItems,
  purchaseShoppingItem,
  shoppingKeys,
  unpurchaseShoppingItem,
  updateShoppingItem,
  type ShoppingFilters,
} from "@/api/shopping";
import type { ShoppingItem, ShoppingItemCreate, ShoppingItemUpdate } from "@/api/types";
import { useToast } from "@/components/toast/useToast";
import { isNotFound } from "@/lib/formErrors";

/** Pending first, grouped by category: the API's default order (category, then name). */
export const PENDING_FILTERS: ShoppingFilters = { is_purchased: false, sort: "category" };
/** Most recent purchases first. */
export const PURCHASED_FILTERS: ShoppingFilters = { is_purchased: true, sort: "-purchased_at" };

export function useShoppingItems(filters: ShoppingFilters, pages: number, enabled = true) {
  return useQuery({
    queryKey: shoppingKeys.list(filters, pages),
    queryFn: () => listShoppingItems(filters, pages),
    placeholderData: keepPreviousData,
    enabled,
  });
}

export function useShoppingSummary() {
  return useQuery({ queryKey: shoppingKeys.summary(), queryFn: getShoppingSummary });
}

export function usePantryOptions(q: string) {
  return useQuery({ queryKey: pantryKeys.options(q), queryFn: () => listPantryOptions(q), placeholderData: keepPreviousData });
}

/** The dashboard shows pending count and total: refresh it with the list. */
function useRefreshShopping() {
  const queryClient = useQueryClient();
  return (alsoPantry = false) =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: shoppingKeys.all }),
      queryClient.invalidateQueries({ queryKey: dashboardKeys.all }),
      alsoPantry && queryClient.invalidateQueries({ queryKey: pantryKeys.all }),
    ]);
}

export function useSaveShoppingItem(item: ShoppingItem | null) {
  const refresh = useRefreshShopping();
  return useMutation({
    mutationFn: (body: ShoppingItemCreate & ShoppingItemUpdate) =>
      item ? updateShoppingItem(item.id, body) : createShoppingItem(body),
    onSuccess: () => refresh(),
    // Deleted on another device: the form closes and the list drops it.
    onError: (error) => (isNotFound(error) ? refresh() : undefined),
  });
}

export const PURCHASE_MUTATION_KEY = ["shopping", "purchase"] as const;

/** Ids of the items whose purchase is in flight (several can be checked in a row). */
export function usePurchasingIds(): string[] {
  return useMutationState({
    filters: { mutationKey: PURCHASE_MUTATION_KEY, status: "pending" },
    select: (mutation) => (mutation.state.variables as ShoppingItem | undefined)?.id ?? "",
  });
}

/** Errors of the list actions (409 already bought, 422 pantry limit, 404) all go to a toast. */
export function usePurchase() {
  const refresh = useRefreshShopping();
  const toast = useToast();
  return useMutation({
    mutationKey: PURCHASE_MUTATION_KEY,
    mutationFn: (item: ShoppingItem) => purchaseShoppingItem(item.id),
    onSuccess: (result) => {
      if (result.pantry_restocked) toast.success(`Despensa reposta: ${result.name}.`);
    },
    onError: (error) => toast.error(errorMessage(error)),
    onSettled: (result) => refresh(Boolean(result?.pantry_restocked)),
  });
}

export function useUnpurchase() {
  const refresh = useRefreshShopping();
  const toast = useToast();
  return useMutation({
    mutationFn: (item: ShoppingItem) => unpurchaseShoppingItem(item.id),
    onSuccess: (item) => toast.success(`"${item.name}" voltou para a lista.`),
    onError: (error) => toast.error(errorMessage(error)),
    onSettled: () => refresh(),
  });
}

export function useCreateFromPantry() {
  const refresh = useRefreshShopping();
  const toast = useToast();
  return useMutation({
    mutationFn: (includeExpired: boolean) => createFromPantry(includeExpired),
    onSuccess: (created) => {
      if (created.length === 0) toast.info("Nada a adicionar: nenhum item da despensa precisa de reposição.");
      else toast.success(created.length === 1 ? "1 item adicionado." : `${created.length} itens adicionados.`);
    },
    onError: (error) => toast.error(errorMessage(error)),
    onSettled: () => refresh(),
  });
}

export function useDeleteShoppingItem() {
  const refresh = useRefreshShopping();
  const toast = useToast();
  return useMutation({
    mutationFn: (item: ShoppingItem) => deleteShoppingItem(item.id),
    onSuccess: () => toast.success("Item excluído."),
    onError: (error) => toast.error(errorMessage(error)),
    onSettled: () => refresh(),
  });
}

export function useClearPurchased() {
  const refresh = useRefreshShopping();
  const toast = useToast();
  return useMutation({
    mutationFn: deletePurchasedItems,
    onSuccess: () => toast.success("Itens comprados removidos da lista."),
    onError: (error) => toast.error(errorMessage(error)),
    onSettled: () => refresh(),
  });
}
