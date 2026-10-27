import { useQuery } from "@tanstack/react-query";
import { dashboardKeys, getDashboard, type DashboardParams } from "@/api/dashboard";
import { financeKeys, getMonthSummary, listBudgets } from "@/api/finance";

/** One week ahead for expiries, reminders and bills; five items per list. */
export const DASHBOARD_PARAMS: DashboardParams = { within: 7, limit: 5 };

// The app turns refetch on focus off by default; a summary of "today" should catch up when the user
// comes back to the tab, so these queries turn it back on.
const LIVE = { refetchOnWindowFocus: true } as const;

export function useDashboard() {
  return useQuery({
    queryKey: dashboardKeys.detail(DASHBOARD_PARAMS),
    queryFn: () => getDashboard(DASHBOARD_PARAMS),
    ...LIVE,
  });
}

/** `month` comes from the dashboard's date (the server's today), so the queries wait for it. */
export function useMonthSummary(month: string | undefined) {
  return useQuery({
    queryKey: financeKeys.summary(month ?? ""),
    queryFn: () => getMonthSummary(month ?? ""),
    enabled: month !== undefined,
    ...LIVE,
  });
}

export function useBudgets(month: string | undefined) {
  return useQuery({
    queryKey: financeKeys.budgets(month ?? ""),
    queryFn: () => listBudgets(month ?? ""),
    enabled: month !== undefined,
    ...LIVE,
  });
}
