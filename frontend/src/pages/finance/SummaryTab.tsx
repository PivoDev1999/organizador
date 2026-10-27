import { ChartBar, Table } from "lucide-react";
import { errorMessage } from "@/api/errors";
import type { CategoryTotals } from "@/api/types";
import { Card } from "@/components/Card";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { SkeletonList } from "@/components/Spinner";
import { formatMonthName } from "@/lib/calendar";
import { formatMoney } from "@/lib/format";
import { TRANSACTION_TYPE_LABELS } from "@/lib/labels";
import { CategoryChart, ChartSlot } from "../dashboard/LazyCharts";
import { MonthCard } from "../dashboard/MonthCard";
import { useMonthSummary } from "../dashboard/queries";

function CategoryTable({ rows, month }: { rows: CategoryTotals[]; month: string }) {
  if (rows.length === 0) return <EmptyState title="Nenhuma transação neste mês." />;
  return (
    <div className="-mx-4 overflow-x-auto px-4">
      <table className="w-full min-w-[32rem] text-left text-sm">
        <caption className="sr-only">Totais por categoria de {formatMonthName(month)}</caption>
        <thead className="border-b border-slate-200 text-slate-700">
          <tr>
            <th scope="col" className="py-2 pr-3 font-medium">
              Categoria
            </th>
            <th scope="col" className="py-2 pr-3 font-medium">
              Tipo
            </th>
            <th scope="col" className="py-2 pr-3 text-right font-medium">
              Total
            </th>
            <th scope="col" className="py-2 pr-3 text-right font-medium">
              Pago
            </th>
            <th scope="col" className="py-2 text-right font-medium">
              Pendente
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((row) => (
            <tr key={`${row.type}-${row.category}`}>
              <th scope="row" className="py-2 pr-3 font-medium text-slate-900">
                {row.category}
              </th>
              <td className="py-2 pr-3 text-slate-700">{TRANSACTION_TYPE_LABELS[row.type]}</td>
              <td className="py-2 pr-3 text-right font-medium whitespace-nowrap text-slate-900">{formatMoney(row.total)}</td>
              <td className="py-2 pr-3 text-right whitespace-nowrap text-slate-700">{formatMoney(row.paid)}</td>
              <td className="py-2 text-right whitespace-nowrap text-slate-700">{formatMoney(row.pending)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Totals of the month (accrual basis), by category, plus the dashboard's expenses chart. */
export function SummaryTab({ month }: { month: string }) {
  const summary = useMonthSummary(month);

  if (summary.isPending) return <SkeletonList rows={4} label="Carregando o resumo..." />;
  if (summary.isError) {
    return (
      <ErrorState
        title="Não foi possível carregar o resumo"
        message={errorMessage(summary.error)}
        onRetry={() => void summary.refetch()}
      />
    );
  }

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <MonthCard month={summary.data} link={false} />
      <ChartSlot title="Despesas por categoria" icon={ChartBar}>
        <CategoryChart month={month} />
      </ChartSlot>
      <Card title="Por categoria" icon={Table} className="lg:col-span-2">
        <CategoryTable rows={summary.data.by_category} month={month} />
      </Card>
    </div>
  );
}
