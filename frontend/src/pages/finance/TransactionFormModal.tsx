import { useId, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import type { Transaction, TransactionType } from "@/api/types";
import { Attachments } from "@/components/attachments/Attachments";
import { Button } from "@/components/Button";
import { FormError } from "@/components/FormError";
import { Modal } from "@/components/Modal";
import { SelectField } from "@/components/SelectField";
import { TextField } from "@/components/TextField";
import { useToast } from "@/components/toast/useToast";
import { useToday } from "@/hooks/useToday";
import { defaultDayOf } from "@/lib/calendar";
import { parseDecimalInput, toDecimalInput, toMoneyString } from "@/lib/decimal";
import { handleFormError, normalizeMessage } from "@/lib/formErrors";
import { labelOptions, TRANSACTION_TYPE_LABELS } from "@/lib/labels";
import { usePetOptions } from "../pets/queries";
import { useSaveTransaction, useTransactionCategories } from "./queries";

interface TransactionForm {
  type: TransactionType;
  amount: string;
  category: string;
  description: string;
  due_date: string;
  pet_id: string;
  paid_on: string;
}

const FIELDS = ["type", "amount", "category", "description", "due_date", "pet_id", "paid_on"] as const;

/** Rule errors of the API on create: payment in the future, or a pet that no longer exists. */
function ruleField(message: string): keyof TransactionForm | undefined {
  const text = normalizeMessage(message);
  if (text.includes("pagamento")) return "paid_on";
  if (text.includes("pet")) return "pet_id";
  return undefined;
}

const required = (message: string) => (value: string) => value.trim() !== "" || message;

export interface TransactionFormModalProps {
  /** null: new transaction. */
  transaction: Transaction | null;
  /** Month on screen ("YYYY-MM"): a new transaction is due in it. */
  month: string;
  /** Pet already filtered on screen, preselected for a new transaction. */
  petId?: string;
  onClose: () => void;
}

/**
 * Create or edit a transaction; editing also shows the attachments. Money goes to the API as a
 * decimal string ("12,9" → "12.90"). "Já paga em" exists only when creating: the PATCH refuses it.
 */
export function TransactionFormModal({ transaction, month, petId, onClose }: TransactionFormModalProps) {
  const formId = useId();
  const categoriesId = useId();
  const toast = useToast();
  const today = useToday();
  const save = useSaveTransaction(transaction);
  const categories = useTransactionCategories();
  const pets = usePetOptions();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    control,
    formState: { errors, isSubmitting },
  } = useForm<TransactionForm>({
    defaultValues: {
      type: transaction?.type ?? "expense",
      amount: toDecimalInput(transaction?.amount, true),
      category: transaction?.category ?? "",
      description: transaction?.description ?? "",
      due_date: transaction?.due_date ?? defaultDayOf(month, today),
      pet_id: transaction ? (transaction.pet_id ?? "") : (petId ?? ""),
      paid_on: "",
    },
  });
  // Controlled: the pets load after the form, and the select must show the chosen one when they arrive.
  const selectedPet = useWatch({ control, name: "pet_id" });
  const petOptions = (pets.data?.items ?? []).map((pet) => ({ value: pet.id, label: pet.name }));

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    const amount = toMoneyString(values.amount);
    if (amount === null) return;
    const body = {
      type: values.type,
      amount,
      category: values.category.trim(),
      description: values.description.trim() || null,
      due_date: values.due_date,
      pet_id: values.pet_id || null,
    };
    try {
      await save.mutateAsync(transaction ? body : { ...body, paid_on: values.paid_on || null });
      toast.success(transaction ? "Transação atualizada." : "Transação criada.");
      onClose();
    } catch (error) {
      handleFormError(error, { fields: FIELDS, setError, setFormError, toast, onNotFound: onClose, ruleField });
    }
  });

  return (
    <Modal
      title={transaction ? "Editar transação" : "Nova transação"}
      onClose={onClose}
      size={transaction ? "lg" : "sm"}
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
      <div className={transaction ? "grid gap-6 md:grid-cols-2" : undefined}>
        <form id={formId} onSubmit={onSubmit} noValidate className="space-y-4" aria-busy={isSubmitting}>
          <FormError message={formError} />
          <div className="grid grid-cols-2 gap-4">
            <SelectField
              label="Tipo"
              options={labelOptions(TRANSACTION_TYPE_LABELS)}
              error={errors.type?.message}
              {...register("type")}
            />
            <TextField
              label="Valor (R$)"
              required
              inputMode="decimal"
              autoComplete="off"
              placeholder="0,00"
              error={errors.amount?.message}
              {...register("amount", { validate: (value) => parseDecimalInput(value, 2).error ?? true })}
            />
          </div>
          <TextField
            label="Categoria"
            required
            autoComplete="off"
            list={categoriesId}
            placeholder="Ex.: Mercado"
            error={errors.category?.message}
            {...register("category", { validate: required("Informe a categoria.") })}
          />
          <datalist id={categoriesId}>
            {categories.data?.map((category) => <option key={category} value={category} />)}
          </datalist>
          <TextField label="Descrição" autoComplete="off" error={errors.description?.message} {...register("description")} />
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <TextField
              label="Vencimento"
              type="date"
              required
              error={errors.due_date?.message}
              {...register("due_date", { required: "Informe o vencimento." })}
            />
            <SelectField
              label="Pet"
              placeholder="Nenhum"
              options={petOptions}
              error={errors.pet_id?.message}
              {...register("pet_id")}
              value={selectedPet}
            />
          </div>
          {!transaction && (
            <TextField
              label="Já paga em"
              type="date"
              max={today}
              hint="Deixe em branco se ainda não foi paga."
              error={errors.paid_on?.message}
              {...register("paid_on")}
            />
          )}
        </form>
        {transaction && <Attachments entityType="transaction" entityId={transaction.id} />}
      </div>
    </Modal>
  );
}
