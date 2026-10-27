import type { Routine, RoutineFrequency } from "@/api/types";
import { ROUTINE_FREQUENCY_LABELS, WEEKDAY_LONG, WEEKDAY_SHORT } from "@/lib/labels";

/** "Diária", "Semanal: seg, qua", "Mensal: dia 31". */
export function describeSchedule(routine: Pick<Routine, "frequency" | "days_of_week" | "day_of_month">): string {
  const label = ROUTINE_FREQUENCY_LABELS[routine.frequency];
  if (routine.frequency === "weekly" && routine.days_of_week?.length) {
    return `${label}: ${routine.days_of_week.map((day) => WEEKDAY_SHORT[day]?.toLowerCase()).join(", ")}`;
  }
  if (routine.frequency === "monthly" && routine.day_of_month) return `${label}: dia ${routine.day_of_month}`;
  return label;
}

export interface ScheduleFields {
  frequency: RoutineFrequency;
  /** Checkbox values ("0" = domingo ... "6" = sábado). */
  days_of_week: string[];
  day_of_month: string;
}

/**
 * Schedule part of the request body. Only the fields of the chosen frequency carry values; the
 * others go as null, so switching an existing routine from monthly to weekly also clears the stored
 * day of the month (PATCH keeps fields that are not sent).
 */
export function scheduleBody({ frequency, days_of_week, day_of_month }: ScheduleFields) {
  return {
    frequency,
    days_of_week: frequency === "weekly" ? days_of_week.map(Number).sort((a, b) => a - b) : null,
    day_of_month: frequency === "monthly" ? Number(day_of_month) : null,
  };
}

export const WEEKDAY_OPTIONS = WEEKDAY_SHORT.map((short, day) => ({ value: String(day), short, long: WEEKDAY_LONG[day] }));
