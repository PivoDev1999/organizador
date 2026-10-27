import { useId, type ComponentProps } from "react";
import { cn } from "@/lib/cn";
import { FieldError, FieldHint } from "./FieldMessage";
import { fieldBorder, fieldClass } from "./fieldStyles";

export interface TextFieldProps extends Omit<ComponentProps<"input">, "id"> {
  label: string;
  error?: string;
  hint?: string;
}

/** Labeled input with hint and error wired to aria-describedby. Works with react-hook-form's register. */
export function TextField({ label, error, hint, className, required, ...props }: TextFieldProps) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy = [hint && hintId, error && errorId].filter(Boolean).join(" ") || undefined;

  return (
    <div className={cn("space-y-1", className)}>
      <label htmlFor={id} className="block text-sm font-medium text-slate-800">
        {label}
        {required && (
          <span aria-hidden="true" className="text-red-700">
            {" "}
            *
          </span>
        )}
      </label>
      <input
        id={id}
        required={required}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        className={cn(fieldClass, fieldBorder(Boolean(error)))}
        {...props}
      />
      {hint && <FieldHint id={hintId}>{hint}</FieldHint>}
      {error && <FieldError id={errorId}>{error}</FieldError>}
    </div>
  );
}
