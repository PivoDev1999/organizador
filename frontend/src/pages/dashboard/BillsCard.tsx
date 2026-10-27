import { Receipt } from "lucide-react";
import type { Dashboard } from "@/api/types";
import { Badge } from "@/components/Badge";
import { PreviewList } from "@/components/PreviewList";
import { SectionCard } from "@/components/SectionCard";
import { sumDecimals } from "@/lib/decimal";
import { formatDate, formatMoney } from "@/lib/format";

export function BillsCard({ upcoming }: { upcoming: Dashboard["finance"]["upcoming"] }) {
  const { items, total } = upcoming;
  // The API sends the first bills only, so the sum is exact for the whole list only when all came.
  const sum = formatMoney(sumDecimals(items.map((bill) => bill.amount)));
  const complete = items.length >= total;

  return (
    <SectionCard title="Contas a pagar" icon={Receipt} to="/financas" linkLabel="Ver finanças">
      {total === 0 ? (
        <p className="text-slate-700">Nenhuma conta a pagar nos próximos 7 dias.</p>
      ) : (
        <>
          <PreviewList
            items={items}
            total={total}
            getKey={(bill) => bill.id}
            renderItem={(bill) => (
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="break-words text-slate-900">{bill.description || bill.category}</p>
                  <p className="flex flex-wrap items-center gap-2 text-sm text-slate-700">
                    vence em {formatDate(bill.due_date)}
                    {bill.overdue && <Badge tone="danger">atrasada</Badge>}
                  </p>
                </div>
                <span className="shrink-0 font-medium text-slate-900">{formatMoney(bill.amount)}</span>
              </div>
            )}
            moreLabel={(n) => `e mais ${n} contas`}
          />
          <p className="mt-2 flex justify-between gap-2 border-t border-slate-200 pt-2 font-semibold text-slate-900">
            <span>{complete ? "Total pendente" : `Total das ${items.length} primeiras`}</span>
            <span>{sum}</span>
          </p>
        </>
      )}
    </SectionCard>
  );
}
