import { Check } from "lucide-react";
import { useId } from "react";
import { cn } from "@/lib/cn";

export interface ToggleChipProps {
  label: string;
  pressed: boolean;
  onToggle: (pressed: boolean) => void;
}

/** On/off filter ("Atrasadas"). A toggle button: screen readers announce "pressionado". */
export function ToggleChip({ label, pressed, onToggle }: ToggleChipProps) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={() => onToggle(!pressed)}
      className={cn(
        "inline-flex min-h-9 items-center gap-1 rounded-full border px-3 text-sm font-medium transition-colors",
        pressed
          ? "border-brand-700 bg-brand-700 text-white hover:bg-brand-800"
          : "border-slate-300 bg-white text-slate-800 hover:bg-slate-100",
      )}
    >
      {pressed && <Check aria-hidden="true" className="size-4" />}
      {label}
    </button>
  );
}

export interface ChipOption<T extends string> {
  value: T;
  label: string;
}

export interface FilterChipsProps<T extends string> {
  /** Group name, read before each chip ("Status"). */
  label: string;
  options: ReadonlyArray<ChipOption<T>>;
  selected: readonly T[];
  onChange: (selected: T[]) => void;
}

/** Multi-select filter as chips. None selected means "no filter". Keeps the order of `options`. */
export function FilterChips<T extends string>({ label, options, selected, onChange }: FilterChipsProps<T>) {
  const labelId = useId();
  if (options.length === 0) return null;
  return (
    <div role="group" aria-labelledby={labelId} className="space-y-1">
      <p id={labelId} className="text-sm font-medium text-slate-800">
        {label}
      </p>
      <div className="flex flex-wrap gap-2">
        {options.map((option) => (
          <ToggleChip
            key={option.value}
            label={option.label}
            pressed={selected.includes(option.value)}
            onToggle={(pressed) =>
              onChange(
                options
                  .map((o) => o.value)
                  .filter((value) => (value === option.value ? pressed : selected.includes(value))),
              )
            }
          />
        ))}
      </div>
    </div>
  );
}
