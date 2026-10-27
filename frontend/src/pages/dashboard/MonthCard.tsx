import { Wallet } from "lucide-react";
import type { MonthTotals } from "@/api/types";
import { SectionCard } from "@/components/SectionCard";
import { cn } from "@/lib/cn";
import { isNegative } from "@/lib/decimal";
import { formatMoney } from "@/lib/format";

function Row({ label, value, detail, negative = false }: { label: string; value: string; detail: string; negative?: boolean }) {
  return (
    <div className="py-2">
      <dt className="text-sm text-slate-700">{label}</dt>
      <dd>
        <span className={cn("text-xl font-semibold", negative ? "text-red-700" : "text-slate-900")}>{formatMoney(value)}</span>
        <span className="block text-sm text-slate-700">{detail}</span>
      </dd>
    </div>
  );
}

/** Totals of a month. `link` adds "Ver finanças" (the dashboard); the finance screen leaves it out. */
export function MonthCard({ month, link = true }: { month: MonthTotals; link?: boolean }) {
  const { income, expense, balance } = month;
  return (
    <SectionCard title="Resumo do mês" icon={Wallet} to={link ? "/financas" : undefined} linkLabel="Ver finanças">
      <dl className="divide-y divide-slate-100">
        <Row label="Receitas" value={income.total} detail={`recebido ${formatMoney(income.paid)} · a receber ${formatMoney(income.pending)}`} />
        <Row label="Despesas" value={expense.total} detail={`pago ${formatMoney(expense.paid)} · a pagar ${formatMoney(expense.pending)}`} />
        <Row
          label="Saldo"
          value={balance.total}
          negative={isNegative(balance.total)}
          detail={`saldo do que já foi pago ${formatMoney(balance.paid)}`}
        />
      </dl>
    </SectionCard>
  );
}
