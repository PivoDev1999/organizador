import { cn } from "@/lib/cn";

export interface ProgressBarProps {
  value: number;
  max: number;
  /** Accessible name, e.g. "Rotinas feitas hoje". */
  label: string;
  /** Text read instead of the bare numbers, e.g. "2 de 5 feitas". */
  valueText?: string;
  className?: string;
  /** Color of the filled part (default: the brand color). */
  barClassName?: string;
}

export function ProgressBar({ value, max, label, valueText, className, barClassName = "bg-brand-600" }: ProgressBarProps) {
  const percent = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0;
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-valuenow={value}
      aria-valuetext={valueText}
      className={cn("h-2.5 w-full overflow-hidden rounded-full bg-slate-200", className)}
    >
      <div className={cn("h-full rounded-full transition-[width]", barClassName)} style={{ width: `${percent}%` }} />
    </div>
  );
}
