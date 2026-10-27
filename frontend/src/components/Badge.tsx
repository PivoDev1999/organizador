import type { ReactNode } from "react";
import { cn } from "@/lib/cn";
import { TONE_STYLES, type Tone } from "./tones";

/** Short label ("atrasado"). Its text carries the meaning, the color only reinforces it. */
export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span className={cn("inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-xs font-medium", TONE_STYLES[tone])}>
      {children}
    </span>
  );
}
