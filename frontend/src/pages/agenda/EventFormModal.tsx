import { Repeat } from "lucide-react";
import { useId, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { errorMessage } from "@/api/errors";
import type { AgendaEvent, EventRecurrence } from "@/api/types";
import { Attachments } from "@/components/attachments/Attachments";
import { Button } from "@/components/Button";
import { CheckboxField } from "@/components/CheckboxField";
import { ErrorState } from "@/components/ErrorState";
import { FormError } from "@/components/FormError";
import { Modal } from "@/components/Modal";
import { SelectField } from "@/components/SelectField";
import { SkeletonList } from "@/components/Spinner";
import { TextAreaField } from "@/components/TextAreaField";
import { TextField } from "@/components/TextField";
import { useToast } from "@/components/toast/useToast";
import { formatTime } from "@/lib/format";
import { handleFormError, normalizeMessage } from "@/lib/formErrors";
import { EVENT_RECURRENCE_LABELS, labelOptions } from "@/lib/labels";
import { useEvent, useSaveEvent } from "./queries";

interface EventForm {
  title: string;
  starts_on: string;
  /** Form only: without a start time the API treats the event as all-day. */
  all_day: boolean;
  start_time: string;
  end_time: string;
  location: string;
  description: string;
  recurrence: EventRecurrence;
  repeat_until: string;
}

const FIELDS = [
  "title",
  "starts_on",
  "start_time",
  "end_time",
  "location",
  "description",
  "recurrence",
  "repeat_until",
] as const;

const RECURRENCES = labelOptions(EVENT_RECURRENCE_LABELS);

/**
 * Field of the API's combination rules (`loc: ["body"]`), by their fixed texts: "Informe o horário
 * de início (start_time)...", "O horário de término (end_time) deve ser depois...", and the two
 * about "repeat_until". Anything else stays a form-level message.
 */
function ruleField(message: string): keyof EventForm | undefined {
  const text = normalizeMessage(message);
  if (text.includes("informe o horario de inicio")) return "start_time";
  if (text.includes("(end_time)")) return "end_time";
  if (text.includes("(repeat_until)")) return "repeat_until";
  return undefined;
}

function toForm(event: AgendaEvent | null, date: string): EventForm {
  return {
    title: event?.title ?? "",
    starts_on: event?.starts_on ?? date,
    all_day: !event?.start_time,
    // The API answers "14:30:00"; the time input works with "14:30".
    start_time: formatTime(event?.start_time),
    end_time: formatTime(event?.end_time),
    location: event?.location ?? "",
    description: event?.description ?? "",
    recurrence: event?.recurrence ?? "none",
    repeat_until: event?.repeat_until ?? "",
  };
}

export interface EventFormModalProps {
  /** null: new event. */
  event: AgendaEvent | null;
  /** Date of a new event (e.g. the day selected in the calendar). */
  defaultDate: string;
  onClose: () => void;
  /** Editing only: "Excluir" closes the form and asks for confirmation. */
  onDelete?: (event: AgendaEvent) => void;
}

/** Create or edit an event; editing also shows the attachments. Recurring events change as a whole. */
export function EventFormModal({ event, defaultDate, onClose, onDelete }: EventFormModalProps) {
  const formId = useId();
  const toast = useToast();
  const save = useSaveEvent(event);
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    setValue,
    control,
    formState: { errors, isSubmitting },
  } = useForm<EventForm>({ defaultValues: toForm(event, defaultDate) });
  const allDay = useWatch({ control, name: "all_day" });
  const recurrence = useWatch({ control, name: "recurrence" });

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    const repeats = values.recurrence !== "none";
    try {
      await save.mutateAsync({
        title: values.title.trim(),
        description: values.description.trim() || null,
        location: values.location.trim() || null,
        starts_on: values.starts_on,
        start_time: values.all_day ? null : values.start_time || null,
        end_time: values.all_day ? null : values.end_time || null,
        recurrence: values.recurrence,
        repeat_until: repeats ? values.repeat_until || null : null,
      });
      toast.success(event ? "Compromisso atualizado." : "Compromisso criado.");
      onClose();
    } catch (error) {
      handleFormError(error, { fields: FIELDS, setError, setFormError, toast, onNotFound: onClose, ruleField });
    }
  });

  const form = (
    <form id={formId} onSubmit={onSubmit} noValidate className="space-y-4" aria-busy={isSubmitting}>
      <FormError message={formError} />
      {event && event.recurrence !== "none" && (
        <p className="flex items-start gap-2 rounded-lg bg-sky-50 p-3 text-sm text-sky-900">
          <Repeat aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          Este compromisso se repete: as alterações valem para todas as repetições.
        </p>
      )}
      <TextField
        label="Título"
        required
        autoComplete="off"
        error={errors.title?.message}
        {...register("title", { validate: (value) => value.trim() !== "" || "Informe o título." })}
      />
      <TextField
        label="Data"
        type="date"
        required
        error={errors.starts_on?.message}
        {...register("starts_on", { deps: ["repeat_until"], validate: (value) => value !== "" || "Informe a data." })}
      />
      <CheckboxField label="Dia inteiro" {...register("all_day")} />
      {!allDay && (
        <div className="grid grid-cols-2 gap-4">
          <TextField
            label="Início"
            type="time"
            required
            error={errors.start_time?.message}
            {...register("start_time", {
              deps: ["end_time"],
              validate: (value, all) => all.all_day || value !== "" || "Informe o horário de início.",
            })}
          />
          <TextField
            label="Fim"
            type="time"
            hint="Opcional."
            error={errors.end_time?.message}
            {...register("end_time", {
              validate: (value, all) =>
                all.all_day ||
                value === "" ||
                all.start_time === "" ||
                value > all.start_time ||
                "O fim deve ser depois do início.",
            })}
          />
        </div>
      )}
      <TextField label="Local" autoComplete="off" error={errors.location?.message} {...register("location")} />
      <TextAreaField label="Observações" error={errors.description?.message} {...register("description")} />
      <SelectField
        label="Repetição"
        options={RECURRENCES}
        hint={recurrence === "monthly" ? "Nos meses mais curtos, cai no último dia." : undefined}
        error={errors.recurrence?.message}
        {...register("recurrence", {
          // Without repetition there is no end date: nothing stale is kept or sent.
          onChange: (change: { target: { value: string } }) => {
            if (change.target.value === "none") setValue("repeat_until", "");
          },
        })}
      />
      {recurrence !== "none" && (
        <TextField
          label="Repetir até"
          type="date"
          hint="Opcional. Em branco, repete sem data para acabar."
          error={errors.repeat_until?.message}
          {...register("repeat_until", {
            validate: (value, all) =>
              all.recurrence === "none" ||
              value === "" ||
              value >= all.starts_on ||
              "Deve ser no mesmo dia ou depois da data do compromisso.",
          })}
        />
      )}
    </form>
  );

  return (
    <Modal
      title={event ? "Editar compromisso" : "Novo compromisso"}
      onClose={onClose}
      size={event ? "lg" : "sm"}
      footer={
        <>
          {event && onDelete && (
            <Button variant="ghost" onClick={() => onDelete(event)} className="mr-auto text-red-700 hover:bg-red-50">
              Excluir
            </Button>
          )}
          <Button variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" form={formId} loading={isSubmitting}>
            Salvar
          </Button>
        </>
      }
    >
      {event ? (
        <div className="grid gap-6 md:grid-cols-2">
          {form}
          <Attachments entityType="event" entityId={event.id} />
        </div>
      ) : (
        form
      )}
    </Modal>
  );
}

export interface EventEditModalProps {
  eventId: string;
  onClose: () => void;
  onDelete: (event: AgendaEvent) => void;
}

/**
 * Editing from the calendar, which only has a summary: loads the event, then shows the form. The form
 * waits for a fetch made after opening (`isFetchedAfterMount`), never a cached copy: its defaults are
 * fixed on mount and the PATCH sends every field. Later background refetches keep the form open.
 */
export function EventEditModal({ eventId, onClose, onDelete }: EventEditModalProps) {
  const query = useEvent(eventId);
  // A failed refetch also counts as "fetched after mount": the old copy must not open the form.
  if (query.data && query.isFetchedAfterMount && !query.isError) {
    return <EventFormModal event={query.data} defaultDate={query.data.starts_on} onClose={onClose} onDelete={onDelete} />;
  }
  return (
    <Modal title="Editar compromisso" onClose={onClose}>
      {query.isError && !query.isFetching ? (
        <ErrorState
          title="Não foi possível abrir o compromisso"
          message={errorMessage(query.error)}
          onRetry={() => void query.refetch()}
        />
      ) : (
        <SkeletonList rows={4} label="Carregando o compromisso..." />
      )}
    </Modal>
  );
}
