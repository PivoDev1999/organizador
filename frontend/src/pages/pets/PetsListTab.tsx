import { PawPrint } from "lucide-react";
import type { PetFilters } from "@/api/pets";
import { errorMessage } from "@/api/errors";
import type { Pet } from "@/api/types";
import { Button } from "@/components/Button";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { FilterChips } from "@/components/FilterChips";
import { LoadMore } from "@/components/LoadMore";
import { SearchField } from "@/components/SearchField";
import { SkeletonList } from "@/components/Spinner";
import { useToday } from "@/hooks/useToday";
import { useUrlFilters } from "@/hooks/useUrlFilters";
import { PetCard } from "./PetCard";
import { usePets, useSpecies } from "./queries";

export interface PetsListTabProps {
  onCreate: () => void;
  onEdit: (pet: Pet) => void;
  onDelete: (pet: Pet) => void;
}

/** Pets as cards, filtered by species and name (in the URL). */
export function PetsListTab({ onCreate, onEdit, onDelete }: PetsListTabProps) {
  const url = useUrlFilters();
  const today = useToday();
  const species = useSpecies();
  const filters: PetFilters = {
    // Any species in the URL is kept (a just-created one may not be in the suggestions yet).
    species: url.params.getAll("species"),
    q: url.getText("q") || undefined,
    sort: "name",
  };
  const pets = usePets(filters, url.pages);
  const hasFilters = Boolean(filters.species?.length || filters.q);
  const speciesOptions = [...new Set([...(species.data ?? []), ...(filters.species ?? [])])].map((value) => ({
    value,
    label: value,
  }));

  let content;
  if (pets.isPending) {
    content = <SkeletonList rows={3} label="Carregando os pets..." />;
  } else if (pets.isError) {
    content = (
      <ErrorState
        title="Não foi possível carregar os pets"
        message={errorMessage(pets.error)}
        onRetry={() => void pets.refetch()}
      />
    );
  } else if (pets.data.items.length === 0) {
    content = hasFilters ? (
      <EmptyState title="Nenhum pet encontrado." description="Tente mudar ou limpar os filtros." />
    ) : (
      <EmptyState
        icon={PawPrint}
        title="Nenhum pet cadastrado."
        description="Cadastre os pets para acompanhar vacinas, consultas e remédios."
        action={<Button onClick={onCreate}>Novo pet</Button>}
      />
    );
  } else {
    content = (
      <>
        <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3" aria-busy={pets.isPlaceholderData}>
          {pets.data.items.map((pet) => (
            <li key={pet.id}>
              <PetCard pet={pet} today={today} onEdit={onEdit} onDelete={onDelete} />
            </li>
          ))}
        </ul>
        <LoadMore
          shown={pets.data.items.length}
          total={pets.data.total}
          loading={pets.isPlaceholderData}
          onLoadMore={url.loadMore}
          canLoadMore={url.canLoadMore}
        />
      </>
    );
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-[minmax(0,20rem)_1fr] sm:items-start">
        <SearchField label="Buscar" placeholder="Nome do pet" value={filters.q ?? ""} onSearch={(q) => url.update({ q })} />
        <FilterChips
          label="Espécies"
          options={speciesOptions}
          selected={filters.species ?? []}
          onChange={(selected) => url.update({ species: selected })}
        />
      </div>
      {content}
    </div>
  );
}
