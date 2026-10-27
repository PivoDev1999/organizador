import { useId, useState } from "react";
import { useForm } from "react-hook-form";
import type { StockAction } from "@/api/pantry";
import type { PantryItem } from "@/api/types";
import { Button } from "@/components/Button";
import { FormError } from "@/components/FormError";
import { Modal } from "@/components/Modal";
import { TextField } from "@/components/TextField";
import { useToast } from "@/components/toast/useToast";
import { normalizeDecimalInput, parseDecimalInput } from "@/lib/decimal";
import { handleFormError } from "@/lib/formErrors";
import { formatQuantity } from "@/lib/format";
import { useChangeStock } from "./queries";

/** Pantry quantities have up to 3 decimals (NUMERIC(12,3)). */
export const QUANTITY_PLACES = 3;

const TEXT: Record<StockAction, { title: string; button: string; done: string }> = {
  consume: { title: "Consumir", button: "Consumir", done: "Baixa registrada." },
  restock: { title: "Repor", button: "Repor", done: "Estoque reposto." },
};

interface StockForm {
  amount: string;
}

export interface StockModalProps {
  item: PantryItem;
  action: StockAction;
  onClose: () => void;
}

/** Quick "Consumir" / "Repor". The amount is checked here for format only; the API has the last word. */
export function StockModal({ item, action, onClose }: StockModalProps) {
  const formId = useId();
  const toast = useToast();
  const change = useChangeStock();
  const [formError, setFormError] = useState<string | null>(null);
  const text = TEXT[action];
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<StockForm>({ defaultValues: { amount: "" } });

  const onSubmit = handleSubmit(async ({ amount }) => {
    setFormError(null);
    const normalized = normalizeDecimalInput(amount, QUANTITY_PLACES);
    if (normalized === null) return;
    try {
      await change.mutateAsync({ item, action, amount: normalized });
      toast.success(text.done);
      onClose();
    } catch (error) {
      // 409 "Quantidade insuficiente." goes to a toast; the dialog stays open to fix the amount.
      handleFormError(error, { fields: ["amount"], setError, setFormError, toast, onNotFound: onClose });
    }
  });

  return (
    <Modal
      title={`${text.title}: ${item.name}`}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" form={formId} loading={isSubmitting}>
            {text.button}
          </Button>
        </>
      }
    >
      <form id={formId} onSubmit={onSubmit} noValidate className="space-y-4" aria-busy={isSubmitting}>
        <p className="text-slate-700">
          Em estoque: {formatQuantity(item.quantity)} {item.unit}
        </p>
        <FormError message={formError} />
        <TextField
          label={`Quantidade (${item.unit})`}
          inputMode="decimal"
          autoComplete="off"
          required
          hint="Use vírgula para decimais, como 0,5."
          error={errors.amount?.message}
          {...register("amount", {
            validate: (value) => parseDecimalInput(value, QUANTITY_PLACES).error ?? true,
          })}
        />
      </form>
    </Modal>
  );
}
