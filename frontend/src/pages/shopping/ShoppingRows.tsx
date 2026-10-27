import { Link2, Pencil, Trash2, Undo2 } from "lucide-react";
import type { ShoppingItem } from "@/api/types";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { formatDateTime, formatMoney, formatQuantity } from "@/lib/format";

function Details({ item }: { item: ShoppingItem }) {
  const parts = [
    item.quantity && `${formatQuantity(item.quantity)}${item.unit ? ` ${item.unit}` : ""}`,
    item.estimated_price && `${formatMoney(item.estimated_price)} cada`,
  ].filter(Boolean);
  if (parts.length === 0 && !item.pantry_item_id) return null;
  return (
    <div className="mt-0.5 flex flex-wrap items-center gap-2 text-sm text-slate-700">
      {parts.length > 0 && <span>{parts.join(" · ")}</span>}
      {item.pantry_item_id && (
        <Badge>
          <Link2 aria-hidden="true" className="mr-1 size-3" />
          despensa
        </Badge>
      )}
    </div>
  );
}

interface ActionsProps {
  item: ShoppingItem;
  onEdit: (item: ShoppingItem) => void;
  onDelete: (item: ShoppingItem) => void;
}

function EditDelete({ item, onEdit, onDelete }: ActionsProps) {
  return (
    <>
      <Button variant="ghost" size="sm" onClick={() => onEdit(item)} aria-label={`Editar ${item.name}`}>
        <Pencil aria-hidden="true" className="size-4" />
      </Button>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => onDelete(item)}
        aria-label={`Excluir ${item.name}`}
        className="text-red-700 hover:bg-red-50"
      >
        <Trash2 aria-hidden="true" className="size-4" />
      </Button>
    </>
  );
}

export interface PendingRowProps extends ActionsProps {
  /** Purchase request in flight: the box shows checked and waits. */
  busy: boolean;
  onPurchase: (item: ShoppingItem) => void;
}

export function PendingRow({ item, busy, onPurchase, onEdit, onDelete }: PendingRowProps) {
  return (
    <div className="flex items-start gap-3 py-2">
      <input
        type="checkbox"
        checked={busy}
        disabled={busy}
        onChange={() => onPurchase(item)}
        aria-label={`Comprado: ${item.name}`}
        className="mt-1 size-5 shrink-0 accent-brand-700"
      />
      <div className="min-w-0 flex-1">
        <button
          type="button"
          onClick={() => onEdit(item)}
          className="max-w-full text-left font-medium break-words text-slate-900 underline-offset-2 hover:underline"
        >
          {item.name}
        </button>
        <Details item={item} />
      </div>
      <div className="flex shrink-0 gap-1">
        <EditDelete item={item} onEdit={onEdit} onDelete={onDelete} />
      </div>
    </div>
  );
}

export interface PurchasedRowProps extends ActionsProps {
  busy: boolean;
  onUnpurchase: (item: ShoppingItem) => void;
}

export function PurchasedRow({ item, busy, onUnpurchase, onEdit, onDelete }: PurchasedRowProps) {
  return (
    <div className="flex flex-col gap-2 py-2 sm:flex-row sm:items-center">
      <div className="min-w-0 flex-1">
        <p className="font-medium break-words text-slate-600 line-through">{item.name}</p>
        <p className="text-sm text-slate-700">
          {item.category}
          {item.purchased_at && ` · comprado em ${formatDateTime(item.purchased_at)}`}
        </p>
      </div>
      <div className="flex shrink-0 gap-1">
        <Button variant="secondary" size="sm" loading={busy} onClick={() => onUnpurchase(item)}>
          <Undo2 aria-hidden="true" className="size-4" />
          Desfazer compra
          <span className="sr-only">: {item.name}</span>
        </Button>
        <EditDelete item={item} onEdit={onEdit} onDelete={onDelete} />
      </div>
    </div>
  );
}
