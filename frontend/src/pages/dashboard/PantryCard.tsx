import { Archive, CalendarX, Clock, PackageMinus, type LucideIcon } from "lucide-react";
import type { Dashboard, PantryItem } from "@/api/types";
import { PreviewList } from "@/components/PreviewList";
import { SectionCard } from "@/components/SectionCard";
import { StatBadge } from "@/components/StatBadge";
import type { Tone } from "@/components/tones";
import { formatDate, formatQuantity } from "@/lib/format";

/** Items shown per group; the "+N" line covers the rest. */
const ITEMS_PER_GROUP = 3;

type Group = keyof Dashboard["pantry"];

const GROUPS: Array<{ key: Group; label: string; tone: Tone; icon: LucideIcon; detail: (item: PantryItem) => string }> = [
  {
    key: "expired",
    label: "vencidos",
    tone: "danger",
    icon: CalendarX,
    detail: (item) => `venceu em ${formatDate(item.expires_on)}`,
  },
  {
    key: "expiring_soon",
    label: "vencem em 7 dias",
    tone: "warning",
    icon: Clock,
    detail: (item) => `vence em ${formatDate(item.expires_on)}`,
  },
  {
    key: "low_stock",
    label: "com estoque baixo",
    tone: "info",
    icon: PackageMinus,
    detail: (item) => `${formatQuantity(item.quantity)} ${item.unit}`,
  },
];

export function PantryCard({ pantry }: { pantry: Dashboard["pantry"] }) {
  const allClear = GROUPS.every(({ key }) => pantry[key].total === 0);

  return (
    <SectionCard title="Despensa" icon={Archive} to="/despensa" linkLabel="Ver despensa">
      <div className="mb-3 flex flex-wrap gap-2">
        {GROUPS.map(({ key, label, tone, icon }) => (
          <StatBadge key={key} value={pantry[key].total} label={label} tone={pantry[key].total > 0 ? tone : "neutral"} icon={icon} />
        ))}
      </div>
      {allClear ? (
        <p className="text-slate-700">Nada vencido, vencendo ou acabando.</p>
      ) : (
        <div className="space-y-3">
          {GROUPS.filter(({ key }) => pantry[key].total > 0).map(({ key, label, detail }) => (
            <div key={key}>
              <h3 className="text-sm font-semibold text-slate-800 first-letter:uppercase">{label}</h3>
              <PreviewList
                items={pantry[key].items}
                total={pantry[key].total}
                max={ITEMS_PER_GROUP}
                getKey={(item) => item.id}
                renderItem={(item) => (
                  <div className="flex items-start justify-between gap-2">
                    <span className="min-w-0 break-words text-slate-900">{item.name}</span>
                    <span className="shrink-0 text-sm text-slate-700">{detail(item)}</span>
                  </div>
                )}
                moreLabel={(n) => `e mais ${n} itens`}
              />
            </div>
          ))}
        </div>
      )}
    </SectionCard>
  );
}
