import { useId, useState } from "react";
import { useForm } from "react-hook-form";
import type { Budget } from "@/api/types";
import { Button } from "@/components/Button";
import { FormError } from "@/components/FormError";
import { Modal } from "@/components/Modal";
import { TextField } from "@/components/TextField";
import { useToast } from "@/components/toast/useToast";
import { formatMonthName } from "@/lib/calendar";
import { parseDecimalInput, toDecimalInput, toMoneyString } from "@/lib/decimal";
import { handleFormError } from "@/lib/formErrors";
import { useSaveBudget, useTransactionCategories } from "./queries";

interface BudgetForm {
  category: string;
  amount: string;
}

const FIELDS = ["category", "amount"] as const;

export interface BudgetFormModalProps {
  /** null: new budget of `month`. Editing changes only the amount (category and month are its identity). */
  budget: Budget | null;
  month: string;
  onClose: () => void;
}

/** 409 ("Já existe orçamento…") goes to a toast and the dialog stays open to pick another category. */
export function BudgetFormModal({ budget, month, onClose }: BudgetFormModalProps) {
  const formId = useId();
  const categoriesId = useId();
  const toast = useToast();
  const save = useSaveBudget(budget, month);
  const categories = useTransactionCategories();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<BudgetForm>({
    defaultValues: { category: budget?.category ?? "", amount: toDecimalInput(budget?.amount, true) },
  });

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    const amount = toMoneyString(values.amount);
    if (amount === null) return;
    try {
      await save.mutateAsync({ category: values.category.trim(), amount });
      toast.success(budget ? "Orçamento atualizado." : "Orçamento criado.");
      onClose();
    } catch (error) {
      handleFormError(error, { fields: FIELDS, setError, setFormError, toast, onNotFound: onClose });
    }
  });

  return (
    <Modal
      title={budget ? `Orçamento: ${budget.category}` : "Novo orçamento"}
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
        <p className="text-slate-700">Mês: {formatMonthName(budget?.month ?? month)}</p>
        <FormError message={formError} />
        {!budget && (
          <>
            <TextField
              label="Categoria"
              required
              autoComplete="off"
              list={categoriesId}
              hint="A mesma categoria das despesas."
              error={errors.category?.message}
              {...register("category", { validate: (value) => value.trim() !== "" || "Informe a categoria." })}
            />
            <datalist id={categoriesId}>
              {categories.data?.map((category) => <option key={category} value={category} />)}
            </datalist>
          </>
        )}
        <TextField
          label="Limite (R$)"
          required
          inputMode="decimal"
          autoComplete="off"
          placeholder="0,00"
          error={errors.amount?.message}
          {...register("amount", { validate: (value) => parseDecimalInput(value, 2).error ?? true })}
        />
      </form>
    </Modal>
  );
}
