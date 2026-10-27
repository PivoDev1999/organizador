import type { FieldValues, Path, UseFormSetError } from "react-hook-form";
import { ApiError, errorMessage, getFieldErrors } from "@/api/errors";
import type { ToastApi } from "@/components/toast/ToastContext";

export interface FormErrorTarget<T extends FieldValues> {
  /** Form fields named like the API's body fields: their 422 errors go under the field. */
  fields: ReadonlyArray<Path<T>>;
  setError: UseFormSetError<T>;
  /** Form-level message (business rules with `loc: ["body"]`, unknown fields, network, 5xx). */
  setFormError: (message: string | null) => void;
  toast: ToastApi;
  /** 404: the record was deleted meanwhile (e.g. on another device). Typically closes the dialog. */
  onNotFound?: () => void;
  /**
   * Field of a business rule error (`loc: ["body"]`, e.g. "data no futuro"), picked by its message;
   * undefined keeps it as a form-level message. The API's rule messages are fixed texts.
   */
  ruleField?: (message: string) => Path<T> | undefined;
}

/** Lowercase without accents ("Próxima" → "proxima"), to match the API's fixed rule messages. */
export function normalizeMessage(message: string): string {
  return message.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
}

/** The record is gone: the mutations refresh their lists on it, the forms close. */
export function isNotFound(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}

/**
 * Routes an error of a form submit: 422 under each field (rule errors as a form-level message),
 * 409 and 404 to a toast (404 also calls `onNotFound`), anything else as a form-level message.
 */
export function handleFormError<T extends FieldValues>(error: unknown, target: FormErrorTarget<T>): void {
  const { fields, setError, setFormError, toast, onNotFound, ruleField } = target;
  if (error instanceof ApiError && (error.status === 409 || error.status === 404)) {
    toast.error(errorMessage(error));
    if (error.status === 404) onNotFound?.();
    return;
  }
  const fieldErrors = getFieldErrors(error);
  const entries = Object.entries(fieldErrors);
  if (entries.length === 0) {
    setFormError(errorMessage(error));
    return;
  }
  const general: string[] = [];
  let focused = false;
  for (const [field, message] of entries) {
    const known = field === "body" ? ruleField?.(message) : fields.find((name) => name === field);
    if (known) {
      setError(known, { type: "server", message }, { shouldFocus: !focused });
      focused = true;
    } else {
      general.push(message);
    }
  }
  setFormError(general.length > 0 ? general.join(" ") : null);
}
