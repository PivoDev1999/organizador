import { useId, useState } from "react";
import { useForm } from "react-hook-form";
import type { PetEvent, PetEventType } from "@/api/types";
import { Attachments } from "@/components/attachments/Attachments";
import { Button } from "@/components/Button";
import { FormError } from "@/components/FormError";
import { Modal } from "@/components/Modal";
import { SelectField } from "@/components/SelectField";
import { TextField } from "@/components/TextField";
import { useToast } from "@/components/toast/useToast";
import { useToday } from "@/hooks/useToday";
import { handleFormError, normalizeMessage } from "@/lib/formErrors";
import { labelOptions, PET_EVENT_TYPE_LABELS } from "@/lib/labels";
import { useSavePetEvent } from "./queries";

interface EventForm {
  type: PetEventType;
  occurred_on: string;
  next_due_on: string;
  description: string;
}

const FIELDS = ["type", "occurred_on", "next_due_on", "description"] as const;

/** Prefill of a new event (e.g. "Registrar agora" of a reminder: same type and description). */
export interface EventDraft {
  type: PetEventType;
  description: string | null;
}

/**
 * Rule errors of the API: "A próxima data não pode ser anterior à data do evento." and "A data do
 * evento não pode ser no futuro." (checked in this order: the first also mentions "data do evento").
 * Anything else stays a form-level message instead of landing under the wrong field.
 */
function ruleField(message: string): keyof EventForm | undefined {
  const text = normalizeMessage(message);
  if (text.includes("proxima data")) return "next_due_on";
  if (text.includes("data do evento")) return "occurred_on";
  return undefined;
}

export interface PetEventFormModalProps {
  petId: string;
  /** Shown in the title ("Novo evento: Mel"). */
  petName?: string;
  /** null: new event. */
  event: PetEvent | null;
  draft?: EventDraft;
  /** Descriptions already used by the pet: reminders group events by the same description. */
  descriptions: readonly string[];
  onClose: () => void;
}

/** Create or edit a pet event; editing also shows its attachments. A new event happens today by default. */
export function PetEventFormModal({ petId, petName, event, draft, descriptions, onClose }: PetEventFormModalProps) {
  const formId = useId();
  const descriptionsId = useId();
  const toast = useToast();
  const today = useToday();
  const save = useSavePetEvent(petId, event);
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<EventForm>({
    defaultValues: {
      type: event?.type ?? draft?.type ?? "vaccine",
      occurred_on: event?.occurred_on ?? today,
      next_due_on: event?.next_due_on ?? "",
      description: event?.description ?? draft?.description ?? "",
    },
  });

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      await save.mutateAsync({
        type: values.type,
        occurred_on: values.occurred_on,
        next_due_on: values.next_due_on || null,
        description: values.description.trim() || null,
      });
      toast.success(event ? "Evento atualizado." : "Evento registrado.");
      onClose();
    } catch (error) {
      handleFormError(error, { fields: FIELDS, setError, setFormError, toast, onNotFound: onClose, ruleField });
    }
  });

  const title = event ? "Editar evento" : "Novo evento";
  return (
    <Modal
      title={petName ? `${title}: ${petName}` : title}
      onClose={onClose}
      size={event ? "lg" : "sm"}
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
      <div className={event ? "grid gap-6 md:grid-cols-2" : undefined}>
        <form id={formId} onSubmit={onSubmit} noValidate className="space-y-4" aria-busy={isSubmitting}>
          <FormError message={formError} />
          <SelectField
            label="Tipo"
            options={labelOptions(PET_EVENT_TYPE_LABELS)}
            error={errors.type?.message}
            {...register("type")}
          />
          <TextField
            label="Descrição"
            autoComplete="off"
            list={descriptionsId}
            placeholder="Ex.: V10"
            hint="Use a mesma descrição nos reforços: o lembrete anterior é resolvido."
            error={errors.description?.message}
            {...register("description")}
          />
          <datalist id={descriptionsId}>
            {descriptions.map((value) => (
              <option key={value} value={value} />
            ))}
          </datalist>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <TextField
              label="Data"
              type="date"
              required
              max={today}
              error={errors.occurred_on?.message}
              {...register("occurred_on", { required: "Informe a data." })}
            />
            <TextField
              label="Próxima data"
              type="date"
              hint="Gera um lembrete."
              error={errors.next_due_on?.message}
              {...register("next_due_on")}
            />
          </div>
        </form>
        {event && <Attachments entityType="pet_event" entityId={event.id} />}
      </div>
    </Modal>
  );
}
