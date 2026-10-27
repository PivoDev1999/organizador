import { useId, useState } from "react";
import { useForm } from "react-hook-form";
import { ApiError } from "@/api/errors";
import type { Transaction } from "@/api/types";
import { Button } from "@/components/Button";
import { FormError } from "@/components/FormError";
import { Modal } from "@/components/Modal";
import { TextField } from "@/components/TextField";
import { useToast } from "@/components/toast/useToast";
import { useToday } from "@/hooks/useToday";
import { formatMoney } from "@/lib/format";
import { handleFormError } from "@/lib/formErrors";
import { usePayTransaction } from "./queries";

interface PayForm {
  paid_on: string;
}

export interface PayModalProps {
  transaction: Transaction;
  onClose: () => void;
}

/**
 * "Pagar": the day of the payment, today by default. Both 422s ("no futuro", a rule error, and
 * "a partir de 01/01/2000", a field error) go under the date; 409 (already paid) to a toast.
 */
export function PayModal({ transaction, onClose }: PayModalProps) {
  const formId = useId();
  const toast = useToast();
  const today = useToday();
  const pay = usePayTransaction();
  const [formError, setFormError] = useState<string | null>(null);
  const income = transaction.type === "income";
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<PayForm>({ defaultValues: { paid_on: today } });

  const onSubmit = handleSubmit(async ({ paid_on }) => {
    setFormError(null);
    try {
      await pay.mutateAsync({ transaction, paidOn: paid_on });
      toast.success(income ? "Recebimento registrado." : "Pagamento registrado.");
      onClose();
    } catch (error) {
      handleFormError(error, {
        fields: ["paid_on"],
        setError,
        setFormError,
        toast,
        onNotFound: onClose,
        ruleField: () => "paid_on",
      });
      if (error instanceof ApiError && error.status === 409) onClose();
    }
  });

  return (
    <Modal
      title={income ? "Registrar recebimento" : "Registrar pagamento"}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" form={formId} loading={isSubmitting}>
            {income ? "Receber" : "Pagar"}
          </Button>
        </>
      }
    >
      <form id={formId} onSubmit={onSubmit} noValidate className="space-y-4" aria-busy={isSubmitting}>
        <p className="text-slate-700">
          <span className="font-medium text-slate-900">{transaction.description || transaction.category}</span> ·{" "}
          {formatMoney(transaction.amount)}
        </p>
        <FormError message={formError} />
        <TextField
          label={income ? "Recebida em" : "Paga em"}
          type="date"
          required
          max={today}
          error={errors.paid_on?.message}
          {...register("paid_on", { required: "Informe a data." })}
        />
      </form>
    </Modal>
  );
}
