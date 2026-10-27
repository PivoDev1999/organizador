import { Copy, Gauge, Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { errorMessage } from "@/api/errors";
import type { Budget } from "@/api/types";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { ProgressBar } from "@/components/ProgressBar";
import { SkeletonList } from "@/components/Spinner";
import type { Tone } from "@/components/tones";
import { formatMonthName, shiftMonth } from "@/lib/calendar";
import { cn } from "@/lib/cn";
import { isNegative, type BudgetLevel } from "@/lib/decimal";
import { formatMoney } from "@/lib/format";
import { BUDGET_LEVEL_LABELS, prepareBudgetData, type BudgetDatum } from "../dashboard/chartData";
import { useBudgets } from "../dashboard/queries";
import { BudgetFormModal } from "./BudgetFormModal";
import { useCopyBudgets, useDeleteBudget } from "./queries";

// Same colors as the dashboard's budget chart (emerald-700, amber-500, red-700); the level is also text.
const LEVEL_BARS: Record<BudgetLevel, string> = { normal: "bg-emerald-700", warning: "bg-amber-500", exceeded: "bg-red-700" };
const LEVEL_TONES: Record<BudgetLevel, Tone> = { normal: "success", warning: "warning", exceeded: "danger" };

function BudgetRow({ item, budget, onEdit, onDelete }: { item: BudgetDatum; budget: Budget; onEdit: () => void; onDelete: () => void }) {
  const negative = isNegative(budget.remaining);
  return (
    <div className="py-3">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium break-words text-slate-900">{budget.category}</span>
            <Badge tone={LEVEL_TONES[item.level]}>{BUDGET_LEVEL_LABELS[item.level]}</Badge>
          </div>
          <p className="mt-0.5 text-sm text-slate-700">
            {formatMoney(budget.spent)} de {formatMoney(budget.amount)} · <span className="font-medium">{item.label}</span>
          </p>
        </div>
        <div className="flex shrink-0 gap-1">
          <Button variant="ghost" size="sm" onClick={onEdit} aria-label={`Editar orçamento de ${budget.category}`}>
            <Pencil aria-hidden="true" className="size-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={onDelete}
            aria-label={`Excluir orçamento de ${budget.category}`}
            className="text-red-700 hover:bg-red-50"
          >
            <Trash2 aria-hidden="true" className="size-4" />
          </Button>
        </div>
      </div>
      <ProgressBar
        value={Math.min(item.value, 100)}
        max={100}
        label={`Uso do orçamento de ${budget.category}`}
        valueText={`${item.label}, ${BUDGET_LEVEL_LABELS[item.level]}`}
        barClassName={LEVEL_BARS[item.level]}
        className="mt-2"
      />
      <p className={cn("mt-1 text-sm", negative ? "font-medium text-red-700" : "text-slate-700")}>
        Restante: {formatMoney(budget.remaining)}
      </p>
    </div>
  );
}

/** Budgets of the month: usage bars with the backend's levels, create/edit/delete and "copy". */
export function BudgetsTab({ month }: { month: string }) {
  const budgets = useBudgets(month);
  const copy = useCopyBudgets();
  const remove = useDeleteBudget();
  const [editing, setEditing] = useState<Budget | "new" | null>(null);
  const [deleting, setDeleting] = useState<Budget | null>(null);
  const previous = shiftMonth(month, -1);

  let content;
  if (budgets.isPending) {
    content = <SkeletonList rows={3} label="Carregando os orçamentos..." />;
  } else if (budgets.isError) {
    content = (
      <ErrorState
        title="Não foi possível carregar os orçamentos"
        message={errorMessage(budgets.error)}
        onRetry={() => void budgets.refetch()}
      />
    );
  } else if (budgets.data.length === 0) {
    content = (
      <EmptyState
        icon={Gauge}
        title={`Nenhum orçamento em ${formatMonthName(month).toLowerCase()}.`}
        description="Defina limites por categoria ou copie os do mês anterior."
      />
    );
  } else {
    content = (
      <ul className="divide-y divide-slate-100">
        {budgets.data.map((budget) => {
          const [item] = prepareBudgetData([budget]);
          return item ? (
            <li key={budget.id}>
              <BudgetRow item={item} budget={budget} onEdit={() => setEditing(budget)} onDelete={() => setDeleting(budget)} />
            </li>
          ) : null;
        })}
      </ul>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap justify-end gap-2">
        <Button
          variant="secondary"
          loading={copy.isPending}
          onClick={() => copy.mutate({ from: previous, to: month })}
          title={`Copia os orçamentos de ${formatMonthName(previous).toLowerCase()}`}
        >
          <Copy aria-hidden="true" className="size-4" />
          Copiar do mês anterior
        </Button>
        <Button onClick={() => setEditing("new")}>
          <Plus aria-hidden="true" className="size-5" />
          Novo orçamento
        </Button>
      </div>
      {content}

      {editing && <BudgetFormModal budget={editing === "new" ? null : editing} month={month} onClose={() => setEditing(null)} />}
      {deleting && (
        <ConfirmDialog
          title="Excluir orçamento?"
          message={`O orçamento de "${deleting.category}" em ${formatMonthName(deleting.month).toLowerCase()} será excluído. As transações não mudam.`}
          loading={remove.isPending}
          onConfirm={() => remove.mutate(deleting, { onSettled: () => setDeleting(null) })}
          onCancel={() => setDeleting(null)}
        />
      )}
    </div>
  );
}
