import { PawPrint } from "lucide-react";
import type { Dashboard } from "@/api/types";
import { Badge } from "@/components/Badge";
import { PreviewList } from "@/components/PreviewList";
import { SectionCard } from "@/components/SectionCard";
import { formatDate } from "@/lib/format";
import { PET_EVENT_TYPE_LABELS } from "@/lib/labels";

export function PetsCard({ pets }: { pets: Dashboard["pets"] }) {
  const { reminders } = pets;
  return (
    <SectionCard title="Pets" icon={PawPrint} to="/pets" linkLabel="Ver pets">
      {reminders.total === 0 ? (
        <p className="text-slate-700">Nenhum lembrete para os próximos 7 dias.</p>
      ) : (
        <PreviewList
          items={reminders.items}
          total={reminders.total}
          getKey={(reminder) => reminder.event_id}
          renderItem={(reminder) => (
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="break-words font-medium text-slate-900">{reminder.pet_name}</p>
                <p className="text-sm text-slate-700">
                  {PET_EVENT_TYPE_LABELS[reminder.type]}
                  {reminder.description && ` · ${reminder.description}`}
                </p>
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1">
                <span className="text-sm text-slate-800">{formatDate(reminder.next_due_on)}</span>
                {reminder.overdue && <Badge tone="danger">atrasado</Badge>}
              </div>
            </div>
          )}
          moreLabel={(n) => `e mais ${n} lembretes`}
        />
      )}
    </SectionCard>
  );
}
