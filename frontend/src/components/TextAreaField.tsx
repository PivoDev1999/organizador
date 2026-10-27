import { useId, type ComponentProps } from "react";
import { cn } from "@/lib/cn";
import { FieldError, FieldHint } from "./FieldMessage";
import { fieldBorder, fieldClass } from "./fieldStyles";

export interface TextAreaFieldProps extends Omit<ComponentProps<"textarea">, "id"> {
  label: string;
  error?: string;
  hint?: string;
}

export function TextAreaField({ label, error, hint, className, rows = 3, ...props }: TextAreaFieldProps) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy = [hint && hintId, error && errorId].filter(Boolean).join(" ") || undefined;

  return (
    <div className={cn("space-y-1", className)}>
      <label htmlFor={id} className="block text-sm font-medium text-slate-800">
        {label}
      </label>
      <textarea
        id={id}
        rows={rows}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        className={cn(fieldClass, fieldBorder(Boolean(error)), "py-2")}
        {...props}
      />
      {hint && <FieldHint id={hintId}>{hint}</FieldHint>}
      {error && <FieldError id={errorId}>{error}</FieldError>}
    </div>
  );
}
