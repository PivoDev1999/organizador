import { CalendarDays, PawPrint, Pencil, Trash2, Undo2 } from "lucide-react";
import type { Transaction } from "@/api/types";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { cn } from "@/lib/cn";
import { formatDate, formatMoney } from "@/lib/format";

/** "2026-10-27" → "27/10". */
function dayMonth(value: string): string {
  return formatDate(value).slice(0, 5);
}

export interface TransactionRowProps {
  transaction: Transaction;
  /** Name of the linked pet, when there is one. */
  petName?: string;
  onPay: (transaction: Transaction) => void;
  onUnpay: (transaction: Transaction) => void;
  onEdit: (transaction: Transaction) => void;
  onDelete: (transaction: Transaction) => void;
}

export function TransactionRow({ transaction: tx, petName, onPay, onUnpay, onEdit, onDelete }: TransactionRowProps) {
  const income = tx.type === "income";
  const title = tx.description || tx.category;
  return (
    <div className="flex flex-col gap-2 py-3 sm:flex-row sm:items-start">
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <button
              type="button"
              onClick={() => onEdit(tx)}
              className="max-w-full text-left font-medium break-words text-slate-900 underline-offset-2 hover:underline"
            >
              {title}
            </button>
            {tx.description && tx.description !== tx.category && <p className="text-sm text-slate-700">{tx.category}</p>}
          </div>
          <p className={cn("shrink-0 text-right font-semibold whitespace-nowrap", income ? "text-emerald-800" : "text-slate-900")}>
            <span className="sr-only">{income ? "Receita" : "Despesa"}: </span>
            <span aria-hidden="true">{income ? "+" : "−"}</span>
            {formatMoney(tx.amount)}
          </p>
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-slate-700">
          <span className={cn("inline-flex items-center gap-1", tx.overdue && "font-medium text-red-800")}>
            <CalendarDays aria-hidden="true" className="size-4" />
            <span className="sr-only">Vencimento:</span>
            {formatDate(tx.due_date)}
          </span>
          {tx.paid_on ? (
            <Badge tone="success">{income ? "recebida" : "paga"} em {dayMonth(tx.paid_on)}</Badge>
          ) : tx.overdue ? (
            <Badge tone="danger">atrasada</Badge>
          ) : (
            <Badge tone="warning">pendente</Badge>
          )}
          {petName && (
            <span className="inline-flex items-center gap-1">
              <PawPrint aria-hidden="true" className="size-4" />
              <span className="sr-only">Pet:</span>
              {petName}
            </span>
          )}
        </div>
      </div>
      <div className="flex shrink-0 flex-wrap justify-end gap-1">
        {tx.paid_on ? (
          <Button variant="ghost" size="sm" onClick={() => onUnpay(tx)} aria-label={`Desfazer pagamento: ${title}`}>
            <Undo2 aria-hidden="true" className="size-4" />
            Desfazer pagamento
          </Button>
        ) : (
          <Button variant="secondary" size="sm" onClick={() => onPay(tx)} aria-label={`${income ? "Receber" : "Pagar"} ${title}`}>
            {income ? "Receber" : "Pagar"}
          </Button>
        )}
        <Button variant="ghost" size="sm" onClick={() => onEdit(tx)} aria-label={`Editar ${title}`}>
          <Pencil aria-hidden="true" className="size-4" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onDelete(tx)}
          aria-label={`Excluir ${title}`}
          className="text-red-700 hover:bg-red-50"
        >
          <Trash2 aria-hidden="true" className="size-4" />
        </Button>
      </div>
    </div>
  );
}
