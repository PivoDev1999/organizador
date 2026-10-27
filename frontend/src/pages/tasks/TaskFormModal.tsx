import { useId, useState } from "react";
import { useForm } from "react-hook-form";
import type { Task, TaskPriority, TaskStatus } from "@/api/types";
import { Attachments } from "@/components/attachments/Attachments";
import { Button } from "@/components/Button";
import { FormError } from "@/components/FormError";
import { Modal } from "@/components/Modal";
import { SelectField } from "@/components/SelectField";
import { TextAreaField } from "@/components/TextAreaField";
import { TextField } from "@/components/TextField";
import { useToast } from "@/components/toast/useToast";
import { handleFormError } from "@/lib/formErrors";
import { labelOptions, TASK_PRIORITY_LABELS, TASK_STATUS_LABELS } from "@/lib/labels";
import { useSaveTask } from "./queries";

interface TaskForm {
  title: string;
  description: string;
  priority: TaskPriority;
  status: TaskStatus;
  due_date: string;
}

const FIELDS = ["title", "description", "priority", "status", "due_date"] as const;

function toForm(task: Task | null): TaskForm {
  return {
    title: task?.title ?? "",
    description: task?.description ?? "",
    priority: task?.priority ?? "medium",
    status: task?.status ?? "todo",
    due_date: task?.due_date ?? "",
  };
}

export interface TaskFormModalProps {
  /** null: new task. */
  task: Task | null;
  onClose: () => void;
}

/** Create or edit a task; editing also shows the attachments. `completed_at` is set by the API only. */
export function TaskFormModal({ task, onClose }: TaskFormModalProps) {
  const formId = useId();
  const toast = useToast();
  const save = useSaveTask(task);
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<TaskForm>({ defaultValues: toForm(task) });

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      await save.mutateAsync({
        title: values.title.trim(),
        description: values.description.trim() || null,
        priority: values.priority,
        status: values.status,
        due_date: values.due_date || null,
      });
      toast.success(task ? "Tarefa atualizada." : "Tarefa criada.");
      onClose();
    } catch (error) {
      handleFormError(error, { fields: FIELDS, setError, setFormError, toast, onNotFound: onClose });
    }
  });

  return (
    <Modal
      title={task ? "Editar tarefa" : "Nova tarefa"}
      onClose={onClose}
      size={task ? "lg" : "sm"}
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
      <div className={task ? "grid gap-6 md:grid-cols-2" : undefined}>
        <form id={formId} onSubmit={onSubmit} noValidate className="space-y-4" aria-busy={isSubmitting}>
          <FormError message={formError} />
          <TextField
            label="Título"
            required
            autoComplete="off"
            error={errors.title?.message}
            {...register("title", { validate: (value) => value.trim() !== "" || "Informe o título." })}
          />
          <TextAreaField label="Descrição" error={errors.description?.message} {...register("description")} />
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <SelectField
              label="Prioridade"
              options={labelOptions(TASK_PRIORITY_LABELS)}
              error={errors.priority?.message}
              {...register("priority")}
            />
            <SelectField
              label="Status"
              options={labelOptions(TASK_STATUS_LABELS)}
              error={errors.status?.message}
              {...register("status")}
            />
          </div>
          <TextField label="Prazo" type="date" error={errors.due_date?.message} {...register("due_date")} />
        </form>
        {task && <Attachments entityType="task" entityId={task.id} />}
      </div>
    </Modal>
  );
}
