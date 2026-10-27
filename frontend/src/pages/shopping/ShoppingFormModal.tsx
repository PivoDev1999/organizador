import { useId, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import type { ShoppingItem } from "@/api/types";
import { Attachments } from "@/components/attachments/Attachments";
import { Button } from "@/components/Button";
import { FormError } from "@/components/FormError";
import { Modal } from "@/components/Modal";
import { SearchField } from "@/components/SearchField";
import { SelectField } from "@/components/SelectField";
import { TextField } from "@/components/TextField";
import { useToast } from "@/components/toast/useToast";
import { normalizeDecimalInput, parseDecimalInput, toDecimalInput, toMoneyString } from "@/lib/decimal";
import { handleFormError } from "@/lib/formErrors";
import { usePantryCategories } from "../pantry/queries";
import { QUANTITY_PLACES } from "../pantry/StockModal";
import { usePantryOptions, useSaveShoppingItem } from "./queries";

interface ShoppingForm {
  name: string;
  category: string;
  quantity: string;
  unit: string;
  estimated_price: string;
  pantry_item_id: string;
}

const FIELDS = ["name", "category", "quantity", "unit", "estimated_price", "pantry_item_id"] as const;

function toForm(item: ShoppingItem | null): ShoppingForm {
  return {
    name: item?.name ?? "",
    category: item?.category ?? "",
    quantity: toDecimalInput(item?.quantity),
    unit: item?.unit ?? "",
    estimated_price: toDecimalInput(item?.estimated_price, true),
    pantry_item_id: item?.pantry_item_id ?? "",
  };
}

const required = (message: string) => (value: string) => value.trim() !== "" || message;

export interface ShoppingFormModalProps {
  /** null: new item. */
  item: ShoppingItem | null;
  /** Categories already on the list, offered as suggestions with the pantry's. */
  knownCategories: readonly string[];
  onClose: () => void;
}

export function ShoppingFormModal({ item, knownCategories, onClose }: ShoppingFormModalProps) {
  const formId = useId();
  const categoriesId = useId();
  const toast = useToast();
  const save = useSaveShoppingItem(item);
  const [pantrySearch, setPantrySearch] = useState("");
  const pantry = usePantryOptions(pantrySearch);
  const pantryCategories = usePantryCategories();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    getValues,
    setValue,
    control,
    formState: { errors, isSubmitting },
  } = useForm<ShoppingForm>({ defaultValues: toForm(item) });

  const pantryItems = pantry.data?.items ?? [];
  // More than one page of pantry items: a search narrows the select down.
  const searchable = pantrySearch !== "" || (pantry.data !== undefined && pantry.data.total > pantryItems.length);
  // Controlled select: the chosen item stays as an option even when a search hides it.
  const selectedId = useWatch({ control, name: "pantry_item_id" });
  const [selectedLabel, setSelectedLabel] = useState<string | null>(null);
  const optionLabel = (p: { name: string; category: string }) => `${p.name} (${p.category})`;
  const pantryOptions = [
    ...(selectedId && !pantryItems.some((p) => p.id === selectedId)
      ? [{ value: selectedId, label: selectedLabel ?? "Item ligado atualmente" }]
      : []),
    ...pantryItems.map((p) => ({ value: p.id, label: optionLabel(p) })),
  ];
  const categories = [...new Set([...knownCategories, ...(pantryCategories.data ?? [])])].sort((a, b) =>
    a.localeCompare(b, "pt-BR"),
  );

  /** Choosing a pantry item fills the empty fields with its data. */
  function onPantryChosen(id: string) {
    setValue("pantry_item_id", id);
    const chosen = pantryItems.find((p) => p.id === id);
    if (!chosen) return;
    setSelectedLabel(optionLabel(chosen));
    const current = getValues();
    if (!current.name.trim()) setValue("name", chosen.name);
    if (!current.category.trim()) setValue("category", chosen.category);
    if (!current.unit.trim()) setValue("unit", chosen.unit);
  }

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      await save.mutateAsync({
        name: values.name.trim(),
        category: values.category.trim(),
        quantity: normalizeDecimalInput(values.quantity, QUANTITY_PLACES),
        unit: values.unit.trim() || null,
        // Money always goes as a string ("12.90"): the API rejects floats.
        estimated_price: toMoneyString(values.estimated_price),
        pantry_item_id: values.pantry_item_id || null,
      });
      toast.success(item ? "Item atualizado." : "Item adicionado à lista.");
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
          <TextField
            label="Categoria"
            required
            autoComplete="off"
            list={categoriesId}
            error={errors.category?.message}
            {...register("category", { validate: required("Informe a categoria.") })}
          />
          <datalist id={categoriesId}>
            {categories.map((category) => (
              <option key={category} value={category} />
            ))}
          </datalist>
          <div className="grid grid-cols-2 gap-4">
            <TextField
              label="Quantidade"
              inputMode="decimal"
              autoComplete="off"
              error={errors.quantity?.message}
              {...register("quantity", {
                validate: (value) =>
                  value.trim() === "" || (parseDecimalInput(value, QUANTITY_PLACES).error ?? true),
              })}
            />
            <TextField
              label="Unidade"
              autoComplete="off"
              placeholder="kg, L, un"
              error={errors.unit?.message}
              {...register("unit")}
            />
          </div>
          <TextField
            label="Preço estimado (por unidade)"
            inputMode="decimal"
            autoComplete="off"
            placeholder="0,00"
            hint="Em reais, como 12,90."
            error={errors.estimated_price?.message}
            {...register("estimated_price", {
              validate: (value) => value.trim() === "" || (parseDecimalInput(value, 2).error ?? true),
            })}
          />
          {searchable && (
            <SearchField label="Buscar item da despensa" value={pantrySearch} onSearch={setPantrySearch} />
          )}
          <SelectField
            label="Item da despensa"
            placeholder={pantry.isPending ? "Carregando..." : "Nenhum"}
            options={pantryOptions}
            hint="Ao comprar, repõe o estoque se tiver quantidade e a mesma unidade."
            error={errors.pantry_item_id?.message ?? (pantry.isError ? "Não foi possível carregar a despensa." : undefined)}
            value={selectedId}
            onChange={(event) => onPantryChosen(event.target.value)}
          />
        </form>
        {item && <Attachments entityType="shopping_item" entityId={item.id} />}
      </div>
    </Modal>
  );
}
