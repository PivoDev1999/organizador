import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { dashboardKeys } from "@/api/dashboard";
import { errorMessage } from "@/api/errors";
import { replaceInPage } from "@/api/pagination";
import {
  changeStock,
  createPantryItem,
  deletePantryItem,
  getPantryAlerts,
  listPantryCategories,
  listPantryItems,
  listPantryLocations,
  pantryKeys,
  updatePantryItem,
  type PantryFilters,
  type StockAction,
} from "@/api/pantry";
import { shoppingKeys } from "@/api/shopping";
import type { Page, PantryItem, PantryItemCreate, PantryItemUpdate } from "@/api/types";
import { useToast } from "@/components/toast/useToast";
import { isNotFound } from "@/lib/formErrors";

export function usePantryItems(filters: PantryFilters, pages: number) {
  return useQuery({
    queryKey: pantryKeys.list(filters, pages),
    queryFn: () => listPantryItems(filters, pages),
    placeholderData: keepPreviousData,
  });
}

export function usePantryAlerts() {
  return useQuery({ queryKey: pantryKeys.alerts(), queryFn: getPantryAlerts });
}

export function usePantryCategories() {
  return useQuery({ queryKey: pantryKeys.categories(), queryFn: listPantryCategories });
}

export function usePantryLocations() {
  return useQuery({ queryKey: pantryKeys.locations(), queryFn: listPantryLocations });
}

/** The dashboard shows pantry alerts: refresh it together with the pantry queries. */
function useRefreshPantry() {
  const queryClient = useQueryClient();
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: pantryKeys.all }),
      queryClient.invalidateQueries({ queryKey: dashboardKeys.all }),
    ]);
}

export function useSavePantryItem(item: PantryItem | null) {
  const queryClient = useQueryClient();
  const refresh = useRefreshPantry();
  // The shopping list shows pantry data (the linked item's select, "from pantry"): refresh it too.
  const refreshAll = () => Promise.all([refresh(), queryClient.invalidateQueries({ queryKey: shoppingKeys.all })]);
  return useMutation({
    mutationFn: (body: PantryItemCreate & PantryItemUpdate) =>
      item ? updatePantryItem(item.id, body) : createPantryItem(body),
    onSuccess: () => refreshAll(),
    // Deleted on another device: the form closes and the lists drop it.
    onError: (error) => (isNotFound(error) ? refreshAll() : undefined),
  });
}

export function useDeletePantryItem() {
  const queryClient = useQueryClient();
  const refresh = useRefreshPantry();
  const toast = useToast();
  return useMutation({
    mutationFn: (item: PantryItem) => deletePantryItem(item.id),
    onSuccess: () => toast.success("Item excluído."),
    onError: (error) => toast.error(errorMessage(error)),
    // Shopping items linked to it lose the link.
    onSettled: () => Promise.all([refresh(), queryClient.invalidateQueries({ queryKey: shoppingKeys.all })]),
  });
}

export interface StockVariables {
  item: PantryItem;
  action: StockAction;
  amount: string;
}

/**
 * Consume or restock. On success the row is replaced with the API's answer in every cached list
 * (the list is not refetched, so the item does not jump around), and the alerts are refreshed.
 */
export function useChangeStock() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ item, action, amount }: StockVariables) => changeStock(item.id, action, amount),
    onSuccess: (updated) => {
      queryClient.setQueriesData<Page<PantryItem>>({ queryKey: pantryKeys.lists() }, (page) =>
        replaceInPage(page, updated.id, () => updated),
      );
      return Promise.all([
        queryClient.invalidateQueries({ queryKey: pantryKeys.alerts() }),
        // The shopping form's select of pantry items (quantities change).
        queryClient.invalidateQueries({ queryKey: pantryKeys.allOptions() }),
        queryClient.invalidateQueries({ queryKey: dashboardKeys.all }),
      ]);
    },
    // Deleted on another device: the dialog closes and the list drops it.
    onError: (error) => (isNotFound(error) ? queryClient.invalidateQueries({ queryKey: pantryKeys.all }) : undefined),
  });
}
