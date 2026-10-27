import { useId, useState } from "react";
import { useForm } from "react-hook-form";
import type { Pet } from "@/api/types";
import { Button } from "@/components/Button";
import { FormError } from "@/components/FormError";
import { Modal } from "@/components/Modal";
import { TextAreaField } from "@/components/TextAreaField";
import { TextField } from "@/components/TextField";
import { useToast } from "@/components/toast/useToast";
import { useToday } from "@/hooks/useToday";
import { normalizeDecimalInput, parseDecimalInput, toDecimalInput } from "@/lib/decimal";
import { handleFormError } from "@/lib/formErrors";
import { useSavePet, useSpecies } from "./queries";

/** Weight is NUMERIC(5,2) in kg. */
const WEIGHT_PLACES = 2;

interface PetForm {
  name: string;
  species: string;
  breed: string;
  birth_date: string;
  weight_kg: string;
  notes: string;
}

const FIELDS = ["name", "species", "breed", "birth_date", "weight_kg", "notes"] as const;

function toForm(pet: Pet | null): PetForm {
  return {
    name: pet?.name ?? "",
    species: pet?.species ?? "",
    breed: pet?.breed ?? "",
    birth_date: pet?.birth_date ?? "",
    weight_kg: toDecimalInput(pet?.weight_kg),
    notes: pet?.notes ?? "",
  };
}

const required = (message: string) => (value: string) => value.trim() !== "" || message;

export interface PetFormModalProps {
  /** null: new pet. */
  pet: Pet | null;
  onClose: () => void;
}

/** Create or edit a pet. The only rule error of the API ("nascimento no futuro") goes under the date. */
export function PetFormModal({ pet, onClose }: PetFormModalProps) {
  const formId = useId();
  const speciesId = useId();
  const toast = useToast();
  const today = useToday();
  const save = useSavePet(pet);
  const species = useSpecies();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<PetForm>({ defaultValues: toForm(pet) });

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      await save.mutateAsync({
        name: values.name.trim(),
        species: values.species.trim(),
        breed: values.breed.trim() || null,
        birth_date: values.birth_date || null,
        weight_kg: values.weight_kg.trim() ? normalizeDecimalInput(values.weight_kg, WEIGHT_PLACES) : null,
        notes: values.notes.trim() || null,
      });
      toast.success(pet ? "Pet atualizado." : "Pet cadastrado.");
      onClose();
    } catch (error) {
      handleFormError(error, {
        fields: FIELDS,
        setError,
        setFormError,
        toast,
        onNotFound: onClose,
        ruleField: () => "birth_date",
      });
    }
  });

  return (
    <Modal
      title={pet ? "Editar pet" : "Novo pet"}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" form={formId} loading={isSubmitting}>
            Salvar
          </Button>
        </>
      }
    >
      <form id={formId} onSubmit={onSubmit} noValidate className="space-y-4" aria-busy={isSubmitting}>
        <FormError message={formError} />
        <TextField
          label="Nome"
          required
          autoComplete="off"
          error={errors.name?.message}
          {...register("name", { validate: required("Informe o nome.") })}
        />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <TextField
            label="Espécie"
            required
            autoComplete="off"
            list={speciesId}
            placeholder="Ex.: Cachorro"
            error={errors.species?.message}
            {...register("species", { validate: required("Informe a espécie.") })}
          />
          <TextField label="Raça" autoComplete="off" error={errors.breed?.message} {...register("breed")} />
        </div>
        <datalist id={speciesId}>
          {species.data?.map((value) => <option key={value} value={value} />)}
        </datalist>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <TextField
            label="Nascimento"
            type="date"
            max={today}
            error={errors.birth_date?.message}
            {...register("birth_date")}
          />
          <TextField
            label="Peso (kg)"
            inputMode="decimal"
            autoComplete="off"
            placeholder="Ex.: 12,5"
            error={errors.weight_kg?.message}
            {...register("weight_kg", {
              validate: (value) => value.trim() === "" || (parseDecimalInput(value, WEIGHT_PLACES).error ?? true),
            })}
          />
        </div>
        <TextAreaField label="Observações" error={errors.notes?.message} {...register("notes")} />
      </form>
    </Modal>
  );
}
