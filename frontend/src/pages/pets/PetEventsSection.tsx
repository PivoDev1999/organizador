import { CalendarClock, Pencil, Plus, Stethoscope, Trash2 } from "lucide-react";
import { useState } from "react";
import { errorMessage } from "@/api/errors";
import type { PetEventFilters } from "@/api/pets";
import type { Pet, PetEvent, PetEventType } from "@/api/types";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { FilterChips } from "@/components/FilterChips";
import { LoadMore } from "@/components/LoadMore";
import { SkeletonList } from "@/components/Spinner";
import { TextField } from "@/components/TextField";
import { useUrlFilters } from "@/hooks/useUrlFilters";
import { formatDate } from "@/lib/format";
import { labelOptions, PET_EVENT_TYPE_LABELS } from "@/lib/labels";
import { PetEventFormModal } from "./PetEventFormModal";
import { useDeletePetEvent, usePetEventDescriptions, usePetEvents } from "./queries";

const TYPES = labelOptions(PET_EVENT_TYPE_LABELS);
const DATE = /^\d{4}-\d{2}-\d{2}$/;

function EventRow({ event, onEdit, onDelete }: { event: PetEvent; onEdit: () => void; onDelete: () => void }) {
  const type = PET_EVENT_TYPE_LABELS[event.type];
  const name = `${type} de ${formatDate(event.occurred_on)}`;
  return (
    <div className="flex items-start gap-3 py-3">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="info">{type}</Badge>
          <span className="font-medium text-slate-900">{formatDate(event.occurred_on)}</span>
        </div>
        {event.description && <p className="mt-1 break-words text-slate-800">{event.description}</p>}
        {event.next_due_on && (
          <p className="mt-1 inline-flex items-center gap-1 text-sm text-slate-700">
            <CalendarClock aria-hidden="true" className="size-4" />
            Próxima: {formatDate(event.next_due_on)}
          </p>
        )}
      </div>
      <div className="flex shrink-0 gap-1">
        <Button variant="ghost" size="sm" onClick={onEdit} aria-label={`Editar ${name}`}>
          <Pencil aria-hidden="true" className="size-4" />
        </Button>
        <Button variant="ghost" size="sm" onClick={onDelete} aria-label={`Excluir ${name}`} className="text-red-700 hover:bg-red-50">
          <Trash2 aria-hidden="true" className="size-4" />
        </Button>
      </div>
    </div>
  );
}

/** History of a pet's events, filtered by type and period (in the URL), with create/edit/delete. */
export function PetEventsSection({ pet }: { pet: Pet }) {
  const url = useUrlFilters();
  const from = url.getText("from");
  const to = url.getText("to");
  const filters: PetEventFilters = {
    type: url.getEnumList<PetEventType>("type", TYPES.map((o) => o.value)),
    from: DATE.test(from) ? from : undefined,
    to: DATE.test(to) ? to : undefined,
  };
  const events = usePetEvents(pet.id, filters, url.pages);
  const remove = useDeletePetEvent();
  const [editing, setEditing] = useState<PetEvent | "new" | null>(null);
  const [deleting, setDeleting] = useState<PetEvent | null>(null);
  const hasFilters = Boolean(filters.type?.length || filters.from || filters.to);
  const descriptions = usePetEventDescriptions(pet.id, editing !== null);

  let content;
  if (events.isPending) {
    content = <SkeletonList rows={3} label="Carregando o histórico..." />;
  } else if (events.isError) {
    content = (
      <ErrorState
        title="Não foi possível carregar o histórico"
        message={errorMessage(events.error)}
        onRetry={() => void events.refetch()}
      />
    );
  } else if (events.data.items.length === 0) {
    content = hasFilters ? (
      <EmptyState title="Nenhum evento encontrado." description="Tente mudar ou limpar os filtros." />
    ) : (
      <EmptyState
        icon={Stethoscope}
        title="Nenhum evento registrado."
        description="Registre vacinas, consultas, remédios e banhos."
        action={<Button onClick={() => setEditing("new")}>Novo evento</Button>}
      />
    );
  } else {
    content = (
      <>
        <ul className="divide-y divide-slate-100" aria-busy={events.isPlaceholderData}>
          {events.data.items.map((event) => (
            <li key={event.id}>
              <EventRow event={event} onEdit={() => setEditing(event)} onDelete={() => setDeleting(event)} />
            </li>
          ))}
        </ul>
        <LoadMore
          shown={events.data.items.length}
          total={events.data.total}
          loading={events.isPlaceholderData}
          onLoadMore={url.loadMore}
          canLoadMore={url.canLoadMore}
        />
      </>
    );
  }

  return (
    <Card
      title="Histórico"
      actions={
        <Button size="sm" onClick={() => setEditing("new")}>
          <Plus aria-hidden="true" className="size-4" />
          Novo evento
        </Button>
      }
    >
      <div className="mb-4 space-y-4">
        <FilterChips label="Tipo" options={TYPES} selected={filters.type ?? []} onChange={(type) => url.update({ type })} />
        <div className="grid grid-cols-2 gap-4 sm:max-w-md">
          <TextField label="De" type="date" value={filters.from ?? ""} onChange={(e) => url.update({ from: e.target.value })} />
          <TextField label="Até" type="date" value={filters.to ?? ""} onChange={(e) => url.update({ to: e.target.value })} />
        </div>
      </div>
      {content}

      {editing && (
        <PetEventFormModal
          petId={pet.id}
          petName={pet.name}
          event={editing === "new" ? null : editing}
          descriptions={descriptions.data ?? []}
          onClose={() => setEditing(null)}
        />
      )}
      {deleting && (
        <ConfirmDialog
          title="Excluir evento?"
          message={`O evento de ${formatDate(deleting.occurred_on)} e os anexos dele serão excluídos.`}
          loading={remove.isPending}
          onConfirm={() => remove.mutate(deleting, { onSettled: () => setDeleting(null) })}
          onCancel={() => setDeleting(null)}
        />
      )}
    </Card>
  );
}
