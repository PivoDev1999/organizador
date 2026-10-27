import { Minus, Pencil, Plus, Trash2 } from "lucide-react";
import type { StockAction } from "@/api/pantry";
import type { PantryItem } from "@/api/types";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { formatDate, formatQuantity } from "@/lib/format";

export interface PantryRowProps {
  item: PantryItem;
  onStock: (item: PantryItem, action: StockAction) => void;
  onEdit: (item: PantryItem) => void;
  onDelete: (item: PantryItem) => void;
}

/** One pantry item. "estoque baixo" and "vencido" come from the API (`low_stock`, `expired`). */
export function PantryRow({ item, onStock, onEdit, onDelete }: PantryRowProps) {
  return (
    <div className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => onEdit(item)}
            className="text-left font-medium break-words text-slate-900 underline-offset-2 hover:underline"
          >
            {item.name}
          </button>
          {item.low_stock && <Badge tone="warning">estoque baixo</Badge>}
          {item.expired && <Badge tone="danger">vencido</Badge>}
        </div>
        <p className="mt-1 text-sm text-slate-700">
          <span className="font-semibold text-slate-900">
            {formatQuantity(item.quantity)} {item.unit}
          </span>
          {" · "}
          {item.category}
          {item.location && ` · ${item.location}`}
          {item.expires_on && (
            <>
              {" · "}
              {item.expired ? "venceu em" : "vence em"} {formatDate(item.expires_on)}
            </>
          )}
        </p>
      </div>
      <div className="flex shrink-0 flex-wrap gap-1">
        <Button variant="secondary" size="sm" onClick={() => onStock(item, "consume")} aria-label={`Consumir ${item.name}`}>
          <Minus aria-hidden="true" className="size-4" />
          Consumir
        </Button>
        <Button variant="secondary" size="sm" onClick={() => onStock(item, "restock")} aria-label={`Repor ${item.name}`}>
          <Plus aria-hidden="true" className="size-4" />
          Repor
        </Button>
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
      </div>
    </div>
  );
}
