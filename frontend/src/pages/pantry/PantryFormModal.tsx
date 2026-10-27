import { useId, useState } from "react";
import { useForm } from "react-hook-form";
import type { PantryItem } from "@/api/types";
import { Attachments } from "@/components/attachments/Attachments";
import { Button } from "@/components/Button";
import { FormError } from "@/components/FormError";
import { Modal } from "@/components/Modal";
import { TextField } from "@/components/TextField";
import { useToast } from "@/components/toast/useToast";
import { normalizeDecimalInput, parseDecimalInput, toDecimalInput } from "@/lib/decimal";
import { handleFormError } from "@/lib/formErrors";
import { usePantryCategories, usePantryLocations, useSavePantryItem } from "./queries";
import { QUANTITY_PLACES } from "./StockModal";

interface PantryForm {
  name: string;
  category: string;
  unit: string;
  quantity: string;
  min_quantity: string;
  expires_on: string;
  location: string;
}

const FIELDS = ["name", "category", "unit", "quantity", "min_quantity", "expires_on", "location"] as const;

function toForm(item: PantryItem | null): PantryForm {
  return {
    name: item?.name ?? "",
    category: item?.category ?? "",
    unit: item?.unit ?? "",
    quantity: toDecimalInput(item?.quantity) || "0",
    min_quantity: toDecimalInput(item?.min_quantity),
    expires_on: item?.expires_on ?? "",
    location: item?.location ?? "",
  };
}

const QUANTITY_RULE = (optional: boolean) => (value: string) =>
  (optional && value.trim() === "") || (parseDecimalInput(value, QUANTITY_PLACES).error ?? true);

const required = (message: string) => (value: string) => value.trim() !== "" || message;

export interface PantryFormModalProps {
  /** null: new item. */
  item: PantryItem | null;
  onClose: () => void;
}

/** Create or edit a pantry item; editing also shows the attachments. */
export function PantryFormModal({ item, onClose }: PantryFormModalProps) {
  const formId = useId();
  const categoriesId = useId();
  const locationsId = useId();
  const toast = useToast();
  const save = useSavePantryItem(item);
  const categories = usePantryCategories();
  const locations = usePantryLocations();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<PantryForm>({ defaultValues: toForm(item) });

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      await save.mutateAsync({
        name: values.name.trim(),
        category: values.category.trim(),
        unit: values.unit.trim(),
        quantity: normalizeDecimalInput(values.quantity, QUANTITY_PLACES) ?? "0",
        min_quantity: normalizeDecimalInput(values.min_quantity, QUANTITY_PLACES),
        expires_on: values.expires_on || null,
        location: values.location.trim() || null,
      });
      toast.success(item ? "Item atualizado." : "Item criado.");
      onClose();
    } catch (error) {
      handleFormError(error, { fields: FIELDS, setError, setFormError, toast, onNotFound: onClose });
    }
  });

  return (
    <Modal
      title={item ? "Editar item" : "Novo item"}
      onClose={onClose}
      size={item ? "lg" : "sm"}
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
      <div className={item ? "grid gap-6 md:grid-cols-2" : undefined}>
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
              label="Categoria"
              required
              autoComplete="off"
              list={categoriesId}
              error={errors.category?.message}
              {...register("category", { validate: required("Informe a categoria.") })}
            />
            <TextField
              label="Local"
              autoComplete="off"
              list={locationsId}
              placeholder="Ex.: Geladeira"
              error={errors.location?.message}
              {...register("location")}
            />
          </div>
          <datalist id={categoriesId}>
            {categories.data?.map((category) => <option key={category} value={category} />)}
          </datalist>
          <datalist id={locationsId}>
            {locations.data?.map((location) => <option key={location} value={location} />)}
          </datalist>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            <TextField
              label="Quantidade"
              required
              inputMode="decimal"
              autoComplete="off"
              error={errors.quantity?.message}
              {...register("quantity", { validate: QUANTITY_RULE(false) })}
            />
            <TextField
              label="Unidade"
              required
              autoComplete="off"
              placeholder="kg, L, un"
              error={errors.unit?.message}
              {...register("unit", { validate: required("Informe a unidade.") })}
            />
            <TextField
              label="Mínimo"
              inputMode="decimal"
              autoComplete="off"
              hint="Avisa quando chegar nele."
              error={errors.min_quantity?.message}
              className="col-span-2 sm:col-span-1"
              {...register("min_quantity", { validate: QUANTITY_RULE(true) })}
            />
          </div>
          <TextField label="Validade" type="date" error={errors.expires_on?.message} {...register("expires_on")} />
        </form>
        {item && <Attachments entityType="pantry_item" entityId={item.id} />}
      </div>
    </Modal>
  );
}
