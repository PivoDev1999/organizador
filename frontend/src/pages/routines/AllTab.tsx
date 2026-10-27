import { Pencil, Repeat, Trash2 } from "lucide-react";
import { errorMessage } from "@/api/errors";
import type { RoutineFilters } from "@/api/routines";
import type { Routine, RoutineFrequency } from "@/api/types";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { FilterChips } from "@/components/FilterChips";
import { LoadMore } from "@/components/LoadMore";
import { SearchField } from "@/components/SearchField";
import { SelectField } from "@/components/SelectField";
import { SkeletonList } from "@/components/Spinner";
import { useUrlFilters } from "@/hooks/useUrlFilters";
import { labelOptions, ROUTINE_FREQUENCY_LABELS } from "@/lib/labels";
import { useRoutines } from "./queries";
import { describeSchedule } from "./schedule";

const FREQUENCIES = labelOptions(ROUTINE_FREQUENCY_LABELS);
const ACTIVE_OPTIONS = [
  { value: "", label: "Todas" },
  { value: "true", label: "Ativas" },
  { value: "false", label: "Inativas" },
];

export interface AllTabProps {
  onOpen: (routine: Routine) => void;
  onCreate: () => void;
  onDelete: (routine: Routine) => void;
}

export function AllTab({ onOpen, onCreate, onDelete }: AllTabProps) {
  const url = useUrlFilters();
  const active = url.getText("is_active");
  const filters: RoutineFilters = {
    frequency: url.getEnumList<RoutineFrequency>("frequency", FREQUENCIES.map((o) => o.value)),
    is_active: active === "true" ? true : active === "false" ? false : undefined,
    q: url.getText("q") || undefined,
  };
  const routines = useRoutines(filters, url.pages);
  const hasFilters = Boolean(filters.frequency?.length || filters.is_active !== undefined || filters.q);

  let content;
  if (routines.isPending) {
    content = <SkeletonList rows={4} label="Carregando rotinas..." />;
  } else if (routines.isError) {
    content = (
      <ErrorState
        title="Não foi possível carregar as rotinas"
        message={errorMessage(routines.error)}
        onRetry={() => void routines.refetch()}
      />
    );
  } else if (routines.data.items.length === 0) {
    content = hasFilters ? (
      <EmptyState title="Nenhuma rotina encontrada." description="Tente mudar ou limpar os filtros." />
    ) : (
      <EmptyState
        icon={Repeat}
        title="Nenhuma rotina ainda."
        description="Crie rotinas diárias, semanais ou mensais."
        action={<Button onClick={onCreate}>Nova rotina</Button>}
      />
    );
  } else {
    content = (
      <>
        <ul className="divide-y divide-slate-100" aria-busy={routines.isPlaceholderData}>
          {routines.data.items.map((routine) => (
            <li key={routine.id} className="flex items-start gap-3 py-3">
              <div className="min-w-0 flex-1">
                <button
                  type="button"
                  onClick={() => onOpen(routine)}
                  className="max-w-full text-left font-medium break-words text-slate-900 underline-offset-2 hover:underline"
                >
                  {routine.name}
                </button>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-slate-700">
                  <span>{describeSchedule(routine)}</span>
                  {routine.time_of_day && <span>· {routine.time_of_day.slice(0, 5)}</span>}
                  {!routine.is_active && <Badge>inativa</Badge>}
                </div>
              </div>
              <div className="flex shrink-0 gap-1">
                <Button variant="ghost" size="sm" onClick={() => onOpen(routine)} aria-label={`Editar ${routine.name}`}>
                  <Pencil aria-hidden="true" className="size-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => onDelete(routine)}
                  aria-label={`Excluir ${routine.name}`}
                  className="text-red-700 hover:bg-red-50"
                >
                  <Trash2 aria-hidden="true" className="size-4" />
                </Button>
              </div>
            </li>
          ))}
        </ul>
        <LoadMore
          shown={routines.data.items.length}
          total={routines.data.total}
          loading={routines.isPlaceholderData}
          onLoadMore={url.loadMore}
          canLoadMore={url.canLoadMore}
        />
      </>
    );
  }

  return (
    <div className="space-y-4">
      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-[1fr_auto]">
          <SearchField label="Buscar" placeholder="Nome da rotina" value={filters.q ?? ""} onSearch={(q) => url.update({ q })} />
          <SelectField
            label="Situação"
            options={ACTIVE_OPTIONS}
            value={active}
            onChange={(event) => url.update({ is_active: event.target.value })}
          />
        </div>
        <FilterChips
          label="Frequência"
          options={FREQUENCIES}
          selected={filters.frequency ?? []}
          onChange={(frequency) => url.update({ frequency })}
        />
      </div>
      {content}
    </div>
  );
}
