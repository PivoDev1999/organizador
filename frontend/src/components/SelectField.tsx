import { useId, type ComponentProps } from "react";
import { cn } from "@/lib/cn";
import { FieldError, FieldHint } from "./FieldMessage";
import { fieldBorder, fieldClass } from "./fieldStyles";

export interface SelectOption {
  value: string;
  label: string;
}

export interface SelectFieldProps extends Omit<ComponentProps<"select">, "id" | "children"> {
  label: string;
  options: SelectOption[];
  /** Text of an empty first option ("Selecione..."); omitted when undefined. */
  placeholder?: string;
  error?: string;
  hint?: string;
}

export function SelectField({
  label,
  options,
  placeholder,
  error,
  hint,
  className,
  required,
  ...props
}: SelectFieldProps) {
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
      <select
        id={id}
        required={required}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        className={cn(fieldClass, fieldBorder(Boolean(error)))}
        {...props}
      >
        {placeholder !== undefined && <option value="">{placeholder}</option>}
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      {hint && <FieldHint id={hintId}>{hint}</FieldHint>}
      {error && <FieldError id={errorId}>{error}</FieldError>}
    </div>
  );
}
