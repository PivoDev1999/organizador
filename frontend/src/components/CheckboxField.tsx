import { useId, type ComponentProps } from "react";
import { cn } from "@/lib/cn";

export interface CheckboxFieldProps extends Omit<ComponentProps<"input">, "id" | "type"> {
  label: string;
}

/** Checkbox with its label as a large click target. Works with react-hook-form's register. */
export function CheckboxField({ label, className, ...props }: CheckboxFieldProps) {
  const id = useId();
  return (
    <div className={cn("flex min-h-11 items-center gap-3", className)}>
      <input id={id} type="checkbox" className="size-5 shrink-0 accent-brand-700" {...props} />
      <label htmlFor={id} className="text-slate-800">
        {label}
      </label>
    </div>
  );
}
