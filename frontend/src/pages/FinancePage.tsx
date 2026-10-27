import { Card } from "@/components/Card";
import { MonthNavigator } from "@/components/MonthNavigator";
import { PageHeader } from "@/components/PageHeader";
import { Tabs } from "@/components/Tabs";
import { useToday } from "@/hooks/useToday";
import { useUrlFilters } from "@/hooks/useUrlFilters";
import { parseMonth } from "@/lib/calendar";
import { monthOf } from "@/lib/format";
import { BudgetsTab } from "./finance/BudgetsTab";
import { SummaryTab } from "./finance/SummaryTab";
import { TRANSACTION_PARAMS, TransactionsTab } from "./finance/TransactionsTab";

type Tab = "transactions" | "summary" | "budgets";
const TABS = [
  { value: "transactions", label: "Transações" },
  { value: "summary", label: "Resumo" },
  { value: "budgets", label: "Orçamentos" },
] as const satisfies ReadonlyArray<{ value: Tab; label: string }>;

const NO_TRANSACTION_FILTERS = Object.fromEntries(TRANSACTION_PARAMS.map((key) => [key, null]));

/**
 * Finance in three tabs sharing the month in the URL (`month=YYYY-MM`, default: the current month by
 * the device's date). Changing the month keeps the tab and its filters and goes back to page 1.
 */
export function FinancePage() {
  const url = useUrlFilters();
  const today = useToday();
  const month = parseMonth(url.params.get("month")) ?? monthOf(today);
  const tab = url.getEnum<Tab>("tab", ["transactions", "summary", "budgets"], "transactions");

  return (
    <>
      <PageHeader title="Finanças" actions={<MonthNavigator month={month} onChange={(next) => url.update({ month: next })} />} />
      <Card>
        <Tabs
          label="Finanças"
          tabs={TABS}
          value={tab}
          // The transaction filters only make sense in their tab; the month stays.
          onChange={(next) => url.update({ tab: next === "transactions" ? null : next, ...NO_TRANSACTION_FILTERS })}
        >
          {tab === "transactions" && <TransactionsTab month={month} />}
          {tab === "summary" && <SummaryTab month={month} />}
          {tab === "budgets" && <BudgetsTab month={month} />}
        </Tabs>
      </Card>
    </>
  );
}
