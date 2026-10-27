import { ShoppingCart } from "lucide-react";
import type { Dashboard } from "@/api/types";
import { SectionCard } from "@/components/SectionCard";
import { formatMoney } from "@/lib/format";

export function ShoppingCard({ shopping }: { shopping: Dashboard["shopping"] }) {
  return (
    <SectionCard title="Mercado" icon={ShoppingCart} to="/mercado" linkLabel="Ver lista">
      {shopping.pending === 0 ? (
        <p className="text-slate-700">A lista de compras está vazia.</p>
      ) : (
        <dl className="grid grid-cols-2 gap-3">
          <div>
            <dt className="text-sm text-slate-700">Itens pendentes</dt>
            <dd className="text-2xl font-semibold text-slate-900">{shopping.pending}</dd>
          </div>
          <div>
            <dt className="text-sm text-slate-700">Total estimado</dt>
            <dd className="text-2xl font-semibold text-slate-900">{formatMoney(shopping.estimated_total)}</dd>
          </div>
        </dl>
      )}
    </SectionCard>
  );
}
