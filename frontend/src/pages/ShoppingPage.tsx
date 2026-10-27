import { Eraser, PackagePlus, Plus, ShoppingCart } from "lucide-react";
import { useState } from "react";
import { errorMessage } from "@/api/errors";
import type { ShoppingItem } from "@/api/types";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { CheckboxField } from "@/components/CheckboxField";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { LoadMore } from "@/components/LoadMore";
import { PageHeader } from "@/components/PageHeader";
import { SkeletonList } from "@/components/Spinner";
import { useUrlFilters } from "@/hooks/useUrlFilters";
import { PurchasedSection } from "./shopping/PurchasedSection";
import {
  PENDING_FILTERS,
  useClearPurchased,
  useCreateFromPantry,
  useDeleteShoppingItem,
  usePurchase,
  usePurchasingIds,
  useShoppingItems,
  useShoppingSummary,
} from "./shopping/queries";
import { ShoppingFormModal } from "./shopping/ShoppingFormModal";
import { PendingRow } from "./shopping/ShoppingRows";
import { ShoppingSummaryCard } from "./shopping/ShoppingSummaryCard";

type Editing = ShoppingItem | "new" | null;

/** Consecutive items of the same category (the API sorts by category, then name). */
function groupByCategory(items: readonly ShoppingItem[]): Array<{ category: string; items: ShoppingItem[] }> {
  const groups: Array<{ category: string; items: ShoppingItem[] }> = [];
  for (const item of items) {
    const last = groups.at(-1);
    if (last && last.category === item.category) last.items.push(item);
    else groups.push({ category: item.category, items: [item] });
  }
  return groups;
}

export function ShoppingPage() {
  const url = useUrlFilters();
  const pending = useShoppingItems(PENDING_FILTERS, url.pages);
  const summary = useShoppingSummary();
  const purchase = usePurchase();
  const purchasing = usePurchasingIds();
  const fromPantry = useCreateFromPantry();
  const clearPurchased = useClearPurchased();
  const remove = useDeleteShoppingItem();
  const [includeExpired, setIncludeExpired] = useState(false);
  const [editing, setEditing] = useState<Editing>(null);
  const [deleting, setDeleting] = useState<ShoppingItem | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);
  const purchasedCount = summary.data?.purchased;

  let content;
  if (pending.isPending) {
    content = <SkeletonList rows={4} label="Carregando a lista..." />;
  } else if (pending.isError) {
    content = (
      <ErrorState
        title="Não foi possível carregar a lista"
        message={errorMessage(pending.error)}
        onRetry={() => void pending.refetch()}
      />
    );
  } else if (pending.data.items.length === 0) {
    content = (
      <EmptyState
        icon={ShoppingCart}
        title="Nada pendente na lista."
        description="Adicione itens ou gere a lista a partir da despensa."
      />
    );
  } else {
    content = (
      <>
        <div className="space-y-4" aria-busy={pending.isPlaceholderData}>
          {groupByCategory(pending.data.items).map((group) => (
            <section key={group.category} aria-label={group.category}>
              <h3 className="border-b border-slate-200 pb-1 text-sm font-semibold tracking-wide text-slate-700 uppercase">
                {group.category}
              </h3>
              <ul className="divide-y divide-slate-100">
                {group.items.map((item) => (
                  <li key={item.id}>
                    <PendingRow
                      item={item}
                      busy={purchasing.includes(item.id)}
                      onPurchase={(target) => purchase.mutate(target)}
                      onEdit={setEditing}
                      onDelete={setDeleting}
                    />
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
        <LoadMore
          shown={pending.data.items.length}
          total={pending.data.total}
          loading={pending.isPlaceholderData}
          onLoadMore={url.loadMore}
          canLoadMore={url.canLoadMore}
        />
      </>
    );
  }

  const knownCategories = [...new Set(pending.data?.items.map((item) => item.category) ?? [])];

  return (
    <>
      <PageHeader
        title="Mercado"
        actions={
          <Button onClick={() => setEditing("new")}>
            <Plus aria-hidden="true" className="size-5" />
            Novo item
          </Button>
        }
      />
      <div className="space-y-4">
        <div className="grid gap-4 md:grid-cols-2">
          <ShoppingSummaryCard />
          <Card title="Da despensa" icon={PackagePlus}>
            <p className="mb-2 text-sm text-slate-700">Adiciona os itens com estoque baixo que ainda não estão na lista.</p>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
              <Button variant="secondary" loading={fromPantry.isPending} onClick={() => fromPantry.mutate(includeExpired)}>
                Gerar da despensa
              </Button>
              <CheckboxField
                label="Incluir vencidos"
                checked={includeExpired}
                onChange={(event) => setIncludeExpired(event.target.checked)}
              />
            </div>
          </Card>
        </div>
        <Card title="Lista de compras">{content}</Card>
        <Card>
          <PurchasedSection count={purchasedCount} onEdit={setEditing} onDelete={setDeleting} />
          {Boolean(purchasedCount) && (
            <div className="mt-3 border-t border-slate-100 pt-3">
              <Button variant="secondary" size="sm" onClick={() => setConfirmClear(true)}>
                <Eraser aria-hidden="true" className="size-4" />
                Limpar comprados
              </Button>
            </div>
          )}
        </Card>
      </div>

      {editing && (
        <ShoppingFormModal
          item={editing === "new" ? null : editing}
          knownCategories={knownCategories}
          onClose={() => setEditing(null)}
        />
      )}
      {deleting && (
        <ConfirmDialog
          title="Excluir item?"
          message={`"${deleting.name}" e os anexos dele serão excluídos.`}
          loading={remove.isPending}
          onConfirm={() => remove.mutate(deleting, { onSettled: () => setDeleting(null) })}
          onCancel={() => setDeleting(null)}
        />
      )}
      {confirmClear && (
        <ConfirmDialog
          title="Limpar comprados?"
          message="Todos os itens comprados, com os anexos deles, serão excluídos da lista. A despensa não muda."
          confirmLabel="Limpar"
          loading={clearPurchased.isPending}
          onConfirm={() => clearPurchased.mutate(undefined, { onSettled: () => setConfirmClear(false) })}
          onCancel={() => setConfirmClear(false)}
        />
      )}
    </>
  );
}
