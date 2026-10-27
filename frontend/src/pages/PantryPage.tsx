import { Package, Plus } from "lucide-react";
import { useState } from "react";
import { errorMessage } from "@/api/errors";
import type { PantryFilters, StockAction } from "@/api/pantry";
import type { PantryItem, PantrySort } from "@/api/types";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { FilterChips, ToggleChip } from "@/components/FilterChips";
import { LoadMore } from "@/components/LoadMore";
import { PageHeader } from "@/components/PageHeader";
import { SearchField } from "@/components/SearchField";
import { SelectField } from "@/components/SelectField";
import { SkeletonList } from "@/components/Spinner";
import { useUrlFilters } from "@/hooks/useUrlFilters";
import { labelOptions, PANTRY_SORT_LABELS } from "@/lib/labels";
import { PantryAlertsCard } from "./pantry/PantryAlertsCard";
import { PantryFormModal } from "./pantry/PantryFormModal";
import { PantryRow } from "./pantry/PantryRow";
import { useDeletePantryItem, usePantryCategories, usePantryItems, usePantryLocations } from "./pantry/queries";
import { StockModal } from "./pantry/StockModal";

const SORTS = labelOptions(PANTRY_SORT_LABELS);
const DEFAULT_SORT: PantrySort = "name";
const EXPIRING_OPTIONS = [
  { value: "", label: "Qualquer data" },
  { value: "3", label: "Vence em até 3 dias" },
  { value: "7", label: "Vence em até 7 dias" },
  { value: "15", label: "Vence em até 15 dias" },
  { value: "30", label: "Vence em até 30 dias" },
];

type Editing = PantryItem | "new" | null;

export function PantryPage() {
  const url = useUrlFilters();
  const categories = usePantryCategories();
  const locations = usePantryLocations();
  const expiring = url.getEnum("expiring_within", EXPIRING_OPTIONS.map((o) => o.value), "");
  const filters: PantryFilters = {
    // Any category in the URL is kept (a just-created one may not be in the suggestions yet).
    category: url.params.getAll("category"),
    location: url.getText("location") || undefined,
    low_stock: url.getFlag("low_stock") || undefined,
    expired: url.getFlag("expired") || undefined,
    expiring_within: expiring ? Number(expiring) : undefined,
    q: url.getText("q") || undefined,
    sort: url.getEnum<PantrySort>("sort", SORTS.map((o) => o.value), DEFAULT_SORT),
  };
  const items = usePantryItems(filters, url.pages);
  const remove = useDeletePantryItem();
  const [editing, setEditing] = useState<Editing>(null);
  const [deleting, setDeleting] = useState<PantryItem | null>(null);
  const [stock, setStock] = useState<{ item: PantryItem; action: StockAction } | null>(null);
  const hasFilters = Boolean(
    filters.category?.length || filters.location || filters.low_stock || filters.expired || filters.expiring_within || filters.q,
  );
  const categoryOptions = [...new Set([...(categories.data ?? []), ...(filters.category ?? [])])].map((value) => ({
    value,
    label: value,
  }));
  const locationOptions = [
    { value: "", label: "Todos os locais" },
    ...[...new Set([...(locations.data ?? []), ...(filters.location ? [filters.location] : [])])].map((value) => ({
      value,
      label: value,
    })),
  ];

  let content;
  if (items.isPending) {
    content = <SkeletonList rows={4} label="Carregando a despensa..." />;
  } else if (items.isError) {
    content = (
      <ErrorState
        title="Não foi possível carregar a despensa"
        message={errorMessage(items.error)}
        onRetry={() => void items.refetch()}
      />
    );
  } else if (items.data.items.length === 0) {
    content = hasFilters ? (
      <EmptyState title="Nenhum item encontrado." description="Tente mudar ou limpar os filtros." />
    ) : (
      <EmptyState
        icon={Package}
        title="A despensa está vazia."
        description="Cadastre o que tem em casa para acompanhar estoque e validade."
        action={<Button onClick={() => setEditing("new")}>Novo item</Button>}
      />
    );
  } else {
    content = (
      <>
        <ul className="divide-y divide-slate-100" aria-busy={items.isPlaceholderData}>
          {items.data.items.map((item) => (
            <li key={item.id}>
              <PantryRow
                item={item}
                onStock={(target, action) => setStock({ item: target, action })}
                onEdit={setEditing}
                onDelete={setDeleting}
              />
            </li>
          ))}
        </ul>
        <LoadMore
          shown={items.data.items.length}
          total={items.data.total}
          loading={items.isPlaceholderData}
          onLoadMore={url.loadMore}
          canLoadMore={url.canLoadMore}
        />
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Despensa"
        actions={
          <Button onClick={() => setEditing("new")}>
            <Plus aria-hidden="true" className="size-5" />
            Novo item
          </Button>
        }
      />
      <div className="space-y-4">
        <PantryAlertsCard />
        <Card>
          <div className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <SearchField
                label="Buscar"
                placeholder="Nome do item"
                value={filters.q ?? ""}
                onSearch={(q) => url.update({ q })}
                className="sm:col-span-2 lg:col-span-1"
              />
              <SelectField
                label="Local"
                options={locationOptions}
                value={filters.location ?? ""}
                onChange={(event) => url.update({ location: event.target.value })}
              />
              <SelectField
                label="Validade"
                options={EXPIRING_OPTIONS}
                value={expiring}
                onChange={(event) => url.update({ expiring_within: event.target.value })}
              />
              <SelectField
                label="Ordenar por"
                options={SORTS}
                value={filters.sort}
                onChange={(event) => url.update({ sort: event.target.value === DEFAULT_SORT ? null : event.target.value })}
              />
            </div>
            <FilterChips
              label="Categorias"
              options={categoryOptions}
              selected={filters.category ?? []}
              onChange={(category) => url.update({ category })}
            />
            <div className="space-y-1">
              <p className="text-sm font-medium text-slate-800">Situação</p>
              <div className="flex flex-wrap gap-2">
                <ToggleChip
                  label="Estoque baixo"
                  pressed={Boolean(filters.low_stock)}
                  onToggle={(low_stock) => url.update({ low_stock })}
                />
                <ToggleChip label="Vencidos" pressed={Boolean(filters.expired)} onToggle={(expired) => url.update({ expired })} />
              </div>
            </div>
          </div>
        </Card>
        <Card title="Itens">{content}</Card>
      </div>

      {editing && <PantryFormModal item={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
      {stock && <StockModal item={stock.item} action={stock.action} onClose={() => setStock(null)} />}
      {deleting && (
        <ConfirmDialog
          title="Excluir item?"
          message={`"${deleting.name}" e os anexos dele serão excluídos. Itens da lista de compras ligados a ele perdem a ligação.`}
          loading={remove.isPending}
          onConfirm={() => remove.mutate(deleting, { onSettled: () => setDeleting(null) })}
          onCancel={() => setDeleting(null)}
        />
      )}
    </>
  );
}
