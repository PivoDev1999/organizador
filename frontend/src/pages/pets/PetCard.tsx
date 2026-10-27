import { PawPrint, Pencil, Trash2 } from "lucide-react";
import { Link } from "react-router";
import type { Pet } from "@/api/types";
import { Button } from "@/components/Button";
import { petAge } from "@/lib/calendar";
import { formatQuantity } from "@/lib/format";

export interface PetCardProps {
  pet: Pet;
  today: string;
  onEdit: (pet: Pet) => void;
  onDelete: (pet: Pet) => void;
}

/** Facts of a pet ("Cachorro · Vira-lata · 3 anos · 12,5 kg"), skipping the unknown ones. */
export function petFacts(pet: Pet, today: string): string[] {
  const age = petAge(pet.birth_date, today);
  return [pet.species, pet.breed, age, pet.weight_kg ? `${formatQuantity(pet.weight_kg)} kg` : null].filter(
    (fact): fact is string => Boolean(fact),
  );
}

export function PetCard({ pet, today, onEdit, onDelete }: PetCardProps) {
  return (
    <article className="flex h-full flex-col rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-start gap-3">
        <span aria-hidden="true" className="rounded-full bg-brand-50 p-2 text-brand-700">
          <PawPrint className="size-6" />
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="text-lg font-semibold break-words text-slate-900">
            <Link to={`/pets/${pet.id}`} className="underline-offset-2 hover:underline">
              {pet.name}
            </Link>
          </h3>
          <p className="text-sm text-slate-700">{petFacts(pet, today).join(" · ")}</p>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap justify-end gap-1 border-t border-slate-100 pt-3">
        <Link
          to={`/pets/${pet.id}`}
          className="inline-flex min-h-9 items-center rounded-lg px-3 text-sm font-medium text-brand-800 hover:bg-slate-100"
        >
          Histórico<span className="sr-only">: {pet.name}</span>
        </Link>
        <Button variant="ghost" size="sm" onClick={() => onEdit(pet)} aria-label={`Editar ${pet.name}`}>
          <Pencil aria-hidden="true" className="size-4" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onDelete(pet)}
          aria-label={`Excluir ${pet.name}`}
          className="text-red-700 hover:bg-red-50"
        >
          <Trash2 aria-hidden="true" className="size-4" />
        </Button>
      </div>
    </article>
  );
}
