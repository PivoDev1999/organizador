import type { CalendarItem, CalendarKind } from "@/api/types";
import type { Tone } from "@/components/tones";
import { cn } from "@/lib/cn";
import { CALENDAR_KIND_LABELS, labelOptions } from "@/lib/labels";

export const CALENDAR_KINDS = labelOptions(CALENDAR_KIND_LABELS);

/** Marker colors: at least 3:1 against white, as non-text indicators need. The text says the rest. */
const DOT_COLORS: Record<CalendarKind, string> = {
  event: "bg-violet-600",
  task: "bg-sky-600",
  bill: "bg-amber-600",
  pet: "bg-rose-600",
};

/** Badge of the read-only items of the day list (events have none: they are the agenda's own). */
export const KIND_TONES: Record<Exclude<CalendarKind, "event">, Tone> = {
  task: "info",
  bill: "warning",
  pet: "danger",
};

/** Colored marker of a kind. Decorative: the legend and the labels carry the meaning. */
export function KindDot({ kind, className }: { kind: CalendarKind; className?: string }) {
  return <span aria-hidden="true" className={cn("inline-block size-2 shrink-0 rounded-full", DOT_COLORS[kind], className)} />;
}

export function KindLegend() {
  return (
    <ul aria-label="Legenda" className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-700">
      {CALENDAR_KINDS.map(({ value, label }) => (
        <li key={value} className="inline-flex items-center gap-1.5">
          <KindDot kind={value} />
          {label}
        </li>
      ))}
    </ul>
  );
}

const COUNT_WORDS: Record<CalendarKind, [string, string]> = {
  event: ["compromisso", "compromissos"],
  task: ["tarefa", "tarefas"],
  bill: ["conta", "contas"],
  pet: ["lembrete de pet", "lembretes de pet"],
};

/** "2 compromissos, 1 conta" for a day's items; "nada marcado" when empty. */
export function describeItems(items: readonly CalendarItem[]): string {
  const parts = CALENDAR_KINDS.flatMap(({ value }) => {
    const count = items.filter((item) => item.kind === value).length;
    const [one, many] = COUNT_WORDS[value];
    return count > 0 ? [`${count} ${count === 1 ? one : many}`] : [];
  });
  return parts.length > 0 ? parts.join(", ") : "nada marcado";
}

/** Distinct kinds of a day, in the legend's order. */
export function kindsOf(items: readonly CalendarItem[]): CalendarKind[] {
  return CALENDAR_KINDS.map((option) => option.value).filter((kind) => items.some((item) => item.kind === kind));
}
