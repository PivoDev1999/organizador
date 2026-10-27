import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/cn";
import { TONE_STYLES, type Tone } from "./tones";

export interface StatBadgeProps {
  value: number | string;
  label: string;
  tone?: Tone;
  icon?: LucideIcon;
}

/** A count with its label, e.g. "3 vencidos". Read as one phrase by screen readers. */
export function StatBadge({ value, label, tone = "neutral", icon: Icon }: StatBadgeProps) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-sm", TONE_STYLES[tone])}>
      {Icon && <Icon aria-hidden="true" className="size-4" />}
      <span className="font-semibold">{value}</span>
      <span>{label}</span>
    </span>
  );
}
