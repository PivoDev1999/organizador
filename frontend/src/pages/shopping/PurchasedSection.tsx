import { ChevronDown } from "lucide-react";
import { useId, useState } from "react";
import { errorMessage } from "@/api/errors";
import type { ShoppingItem } from "@/api/types";
import { ErrorState } from "@/components/ErrorState";
import { LoadMore } from "@/components/LoadMore";
import { SkeletonList } from "@/components/Spinner";
import { cn } from "@/lib/cn";
import { PURCHASED_FILTERS, useShoppingItems, useUnpurchase } from "./queries";
import { PurchasedRow } from "./ShoppingRows";

export interface PurchasedSectionProps {
  count: number | undefined;
  onEdit: (item: ShoppingItem) => void;
  onDelete: (item: ShoppingItem) => void;
}

/** "Comprados", collapsed by default; its list is only fetched when opened. */
export function PurchasedSection({ count, onEdit, onDelete }: PurchasedSectionProps) {
  const panelId = useId();
  const [open, setOpen] = useState(false);
  const [pages, setPages] = useState(1);
  const purchased = useShoppingItems(PURCHASED_FILTERS, pages, open);
  const unpurchase = useUnpurchase();

  let content;
  if (purchased.isPending) {
    content = <SkeletonList rows={2} label="Carregando comprados..." />;
  } else if (purchased.isError) {
    content = (
      <ErrorState
        title="Não foi possível carregar os comprados"
        message={errorMessage(purchased.error)}
        onRetry={() => void purchased.refetch()}
      />
    );
  } else if (purchased.data.items.length === 0) {
    content = <p className="py-2 text-slate-700">Nenhum item comprado.</p>;
  } else {
    content = (
      <>
        <ul className="divide-y divide-slate-100">
          {purchased.data.items.map((item) => (
            <li key={item.id}>
              <PurchasedRow
                item={item}
                busy={unpurchase.isPending && unpurchase.variables.id === item.id}
                onUnpurchase={(target) => unpurchase.mutate(target)}
                onEdit={onEdit}
                onDelete={onDelete}
              />
            </li>
          ))}
        </ul>
        <LoadMore
          shown={purchased.data.items.length}
          total={purchased.data.total}
          loading={purchased.isPlaceholderData}
          onLoadMore={() => setPages((n) => n + 1)}
        />
      </>
    );
  }

  return (
    <div>
      <h2>
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen((value) => !value)}
          className="flex min-h-11 w-full items-center justify-between gap-2 rounded-lg text-left text-lg font-semibold text-slate-900"
        >
          <span>Comprados{count !== undefined && ` (${count})`}</span>
          <ChevronDown aria-hidden="true" className={cn("size-5 transition-transform", open && "rotate-180")} />
        </button>
      </h2>
      <div id={panelId} hidden={!open}>
        {open && content}
      </div>
    </div>
  );
}
