import { useId, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import type { Routine, RoutineFrequency } from "@/api/types";
import { Attachments } from "@/components/attachments/Attachments";
import { Button } from "@/components/Button";
import { CheckboxField } from "@/components/CheckboxField";
import { FieldError } from "@/components/FieldMessage";
import { FormError } from "@/components/FormError";
import { Modal } from "@/components/Modal";
import { SelectField } from "@/components/SelectField";
import { TextAreaField } from "@/components/TextAreaField";
import { TextField } from "@/components/TextField";
import { useToast } from "@/components/toast/useToast";
import { handleFormError } from "@/lib/formErrors";
import { labelOptions, ROUTINE_FREQUENCY_LABELS } from "@/lib/labels";
import { useSaveRoutine } from "./queries";
import { RoutineHistory } from "./RoutineHistory";
import { scheduleBody, WEEKDAY_OPTIONS } from "./schedule";

interface RoutineForm {
  name: string;
  description: string;
  frequency: RoutineFrequency;
  days_of_week: string[];
  day_of_month: string;
  time_of_day: string;
  is_active: boolean;
}

const FIELDS = ["name", "description", "frequency", "days_of_week", "day_of_month", "time_of_day", "is_active"] as const;

function toForm(routine: Routine | null): RoutineForm {
  return {
    name: routine?.name ?? "",
    description: routine?.description ?? "",
    frequency: routine?.frequency ?? "daily",
    days_of_week: routine?.days_of_week?.map(String) ?? [],
    day_of_month: routine?.day_of_month ? String(routine.day_of_month) : "",
    // The API answers "07:30:00"; the time input works with "07:30".
    time_of_day: routine?.time_of_day?.slice(0, 5) ?? "",
    is_active: routine?.is_active ?? true,
  };
}

export interface RoutineFormModalProps {
  /** null: new routine. */
  routine: Routine | null;
  onClose: () => void;
}

/** Create or edit a routine; editing also shows its history and attachments. */
export function RoutineFormModal({ routine, onClose }: RoutineFormModalProps) {
  const formId = useId();
  const daysErrorId = useId();
  const toast = useToast();
  const save = useSaveRoutine(routine);
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    setValue,
    control,
    formState: { errors, isSubmitting },
  } = useForm<RoutineForm>({ defaultValues: toForm(routine) });
  const frequency = useWatch({ control, name: "frequency" });

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      await save.mutateAsync({
        name: values.name.trim(),
        description: values.description.trim() || null,
        ...scheduleBody(values),
        time_of_day: values.time_of_day || null,
        is_active: values.is_active,
      });
      toast.success(routine ? "Rotina atualizada." : "Rotina criada.");
      onClose();
    } catch (error) {
      handleFormError(error, { fields: FIELDS, setError, setFormError, toast, onNotFound: onClose });
    }
  });

  const form = (
    <form id={formId} onSubmit={onSubmit} noValidate className="space-y-4" aria-busy={isSubmitting}>
      <FormError message={formError} />
      <TextField
        label="Nome"
        required
        autoComplete="off"
        error={errors.name?.message}
        {...register("name", { validate: (value) => value.trim() !== "" || "Informe o nome." })}
      />
      <TextAreaField label="Descrição" error={errors.description?.message} {...register("description")} />
      <SelectField
        label="Frequência"
        options={labelOptions(ROUTINE_FREQUENCY_LABELS)}
        error={errors.frequency?.message}
        {...register("frequency", {
          // The fields of the previous frequency are cleared, so nothing stale is shown or sent.
          onChange: () => {
            setValue("days_of_week", []);
            setValue("day_of_month", "");
          },
        })}
      />
      {frequency === "weekly" && (
        <fieldset aria-describedby={errors.days_of_week ? daysErrorId : undefined} className="space-y-1">
          <legend className="text-sm font-medium text-slate-800">
            Dias da semana
            <span aria-hidden="true" className="text-red-700">
              {" "}
              *
            </span>
          </legend>
          <div className="flex flex-wrap gap-2">
            {WEEKDAY_OPTIONS.map((day) => (
              <label
                key={day.value}
                className="flex min-h-11 cursor-pointer items-center gap-2 rounded-lg border border-slate-300 px-3 has-checked:border-brand-700 has-checked:bg-brand-50"
              >
                <input
                  type="checkbox"
                  value={day.value}
                  aria-label={day.long}
                  className="size-4 accent-brand-700"
                  {...register("days_of_week", {
                    validate: (value, all) =>
                      all.frequency !== "weekly" || value.length > 0 || "Escolha pelo menos um dia.",
                  })}
                />
                <span aria-hidden="true">{day.short}</span>
              </label>
            ))}
          </div>
          {errors.days_of_week?.message && <FieldError id={daysErrorId}>{errors.days_of_week.message}</FieldError>}
        </fieldset>
      )}
      {frequency === "monthly" && (
        <TextField
          label="Dia do mês"
          type="number"
          inputMode="numeric"
          min={1}
          max={31}
          required
          hint="Nos meses mais curtos, cai no último dia."
          error={errors.day_of_month?.message}
          {...register("day_of_month", {
            validate: (value, all) => {
              if (all.frequency !== "monthly") return true;
              const day = Number(value);
              return (Number.isInteger(day) && day >= 1 && day <= 31) || "Informe um dia de 1 a 31.";
            },
          })}
        />
      )}
      <TextField label="Horário" type="time" hint="Opcional." error={errors.time_of_day?.message} {...register("time_of_day")} />
      <CheckboxField label="Ativa" {...register("is_active")} />
    </form>
  );

  return (
    <Modal
      title={routine ? "Editar rotina" : "Nova rotina"}
      onClose={onClose}
      size={routine ? "lg" : "sm"}
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
      {routine ? (
        <div className="grid gap-6 md:grid-cols-2">
          {form}
          <div className="space-y-6">
            <RoutineHistory routineId={routine.id} />
            <Attachments entityType="routine" entityId={routine.id} />
          </div>
        </div>
      ) : (
        form
      )}
    </Modal>
  );
}
