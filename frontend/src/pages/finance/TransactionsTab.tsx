import { Plus, Receipt } from "lucide-react";
import { useState } from "react";
import { errorMessage } from "@/api/errors";
import type { TransactionFilters } from "@/api/finance";
import type { Transaction, TransactionSort, TransactionStatus, TransactionType } from "@/api/types";
import { Button } from "@/components/Button";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { FilterChips } from "@/components/FilterChips";
import { LoadMore } from "@/components/LoadMore";
import { SearchField } from "@/components/SearchField";
import { SelectField } from "@/components/SelectField";
import { SkeletonList } from "@/components/Spinner";
import { useUrlFilters } from "@/hooks/useUrlFilters";
import { formatMonthName } from "@/lib/calendar";
import { isUuid } from "@/lib/uuid";
import {
  labelOptions,
  TRANSACTION_SORT_LABELS,
  TRANSACTION_STATUS_LABELS,
  TRANSACTION_TYPE_LABELS,
} from "@/lib/labels";
import { usePetOptions } from "../pets/queries";
import { PayModal } from "./PayModal";
import { useDeleteTransaction, useTransactionCategories, useTransactions, useUnpayTransaction } from "./queries";
import { TransactionFormModal } from "./TransactionFormModal";
import { TransactionRow } from "./TransactionRow";

const TYPES = labelOptions(TRANSACTION_TYPE_LABELS);
const STATUSES = labelOptions(TRANSACTION_STATUS_LABELS);
const SORTS = labelOptions(TRANSACTION_SORT_LABELS);
const DEFAULT_SORT: TransactionSort = "due_date";

/** Query string keys of this tab (dropped when switching tabs). */
export const TRANSACTION_PARAMS = ["type", "status", "category", "pet_id", "q", "sort"] as const;

/** null: closed; "new": creating; a transaction: editing. */
type Editing = Transaction | "new" | null;

/** Transactions of the month with filters in the URL (`month` only: no due_from/due_to). */
export function TransactionsTab({ month }: { month: string }) {
  const url = useUrlFilters();
  const categories = useTransactionCategories();
  const pets = usePetOptions();
  const filters: TransactionFilters = {
    month,
    type: url.getEnumList<TransactionType>("type", TYPES.map((o) => o.value)),
    status: url.getEnumList<TransactionStatus>("status", STATUSES.map((o) => o.value)),
    // Any category in the URL is kept (a just-created one may not be in the suggestions yet).
    category: url.params.getAll("category"),
    // An edited URL with a pet_id that is not a UUID is ignored (the API would answer 422).
    pet_id: isUuid(url.getText("pet_id")) ? url.getText("pet_id") : undefined,
    q: url.getText("q") || undefined,
    sort: url.getEnum<TransactionSort>("sort", SORTS.map((o) => o.value), DEFAULT_SORT),
  };
  const transactions = useTransactions(filters, url.pages);
  const unpay = useUnpayTransaction();
  const remove = useDeleteTransaction();
  const [editing, setEditing] = useState<Editing>(null);
  const [paying, setPaying] = useState<Transaction | null>(null);
  const [deleting, setDeleting] = useState<Transaction | null>(null);
  const hasFilters = Boolean(
    filters.type?.length || filters.status?.length || filters.category?.length || filters.pet_id || filters.q,
  );

  const petNames = new Map((pets.data?.items ?? []).map((pet) => [pet.id, pet.name]));
  const petOptions = [
    { value: "", label: "Todos" },
    ...(pets.data?.items ?? []).map((pet) => ({ value: pet.id, label: pet.name })),
    // A pet in the URL that is not in the list (removed meanwhile) still shows as selected.
    ...(filters.pet_id && pets.data && !petNames.has(filters.pet_id) ? [{ value: filters.pet_id, label: "Pet removido" }] : []),
  ];
  const categoryOptions = [...new Set([...(categories.data ?? []), ...(filters.category ?? [])])].map((value) => ({
    value,
    label: value,
  }));

  let content;
  if (transactions.isPending) {
    content = <SkeletonList rows={4} label="Carregando as transações..." />;
  } else if (transactions.isError) {
    content = (
      <ErrorState
        title="Não foi possível carregar as transações"
        message={errorMessage(transactions.error)}
        onRetry={() => void transactions.refetch()}
      />
    );
  } else if (transactions.data.items.length === 0) {
    content = hasFilters ? (
      <EmptyState
        title="Nenhuma transação encontrada."
        description={
          filters.pet_id
            ? "Este pet pode ter gastos em outros meses — use as setas do mês."
            : "Tente mudar ou limpar os filtros."
        }
      />
    ) : (
      <EmptyState
        icon={Receipt}
        title={`Nenhuma transação em ${formatMonthName(month).toLowerCase()}.`}
        description="Registre contas, compras e receitas para acompanhar o mês."
        action={<Button onClick={() => setEditing("new")}>Nova transação</Button>}
      />
    );
  } else {
    content = (
      <>
        <ul className="divide-y divide-slate-100" aria-busy={transactions.isPlaceholderData}>
          {transactions.data.items.map((tx) => (
            <li key={tx.id}>
              <TransactionRow
                transaction={tx}
                petName={tx.pet_id ? petNames.get(tx.pet_id) : undefined}
                onPay={setPaying}
                onUnpay={(target) => unpay.mutate(target)}
                onEdit={(target) => setEditing(target)}
                onDelete={setDeleting}
              />
            </li>
          ))}
        </ul>
        <LoadMore
          shown={transactions.data.items.length}
          total={transactions.data.total}
          loading={transactions.isPlaceholderData}
          onLoadMore={url.loadMore}
          canLoadMore={url.canLoadMore}
        />
      </>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button onClick={() => setEditing("new")}>
          <Plus aria-hidden="true" className="size-5" />
          Nova transação
        </Button>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <SearchField
          label="Buscar"
          placeholder="Descrição"
          value={filters.q ?? ""}
          onSearch={(q) => url.update({ q })}
          className="sm:col-span-2 lg:col-span-1"
        />
        <SelectField
          label="Pet"
          options={petOptions}
          value={filters.pet_id ?? ""}
          onChange={(event) => url.update({ pet_id: event.target.value })}
        />
        <SelectField
          label="Ordenar por"
          options={SORTS}
          value={filters.sort}
          onChange={(event) => url.update({ sort: event.target.value === DEFAULT_SORT ? null : event.target.value })}
        />
      </div>
      <div className="flex flex-wrap gap-x-6 gap-y-3">
        <FilterChips label="Tipo" options={TYPES} selected={filters.type ?? []} onChange={(type) => url.update({ type })} />
        <FilterChips
          label="Situação"
          options={STATUSES}
          selected={filters.status ?? []}
          onChange={(status) => url.update({ status })}
        />
      </div>
      <FilterChips
        label="Categorias"
        options={categoryOptions}
        selected={filters.category ?? []}
        onChange={(category) => url.update({ category })}
      />
      {content}

      {editing && (
        <TransactionFormModal
          transaction={editing === "new" ? null : editing}
          month={month}
          petId={filters.pet_id ?? undefined}
          onClose={() => setEditing(null)}
        />
      )}
      {paying && <PayModal transaction={paying} onClose={() => setPaying(null)} />}
      {deleting && (
        <ConfirmDialog
          title="Excluir transação?"
          message={`"${deleting.description || deleting.category}" e os anexos dela serão excluídos.`}
          loading={remove.isPending}
          onConfirm={() => remove.mutate(deleting, { onSettled: () => setDeleting(null) })}
          onCancel={() => setDeleting(null)}
        />
      )}
    </div>
  );
}
