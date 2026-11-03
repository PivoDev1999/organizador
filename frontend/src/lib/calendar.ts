// Calendar helpers on the API's date texts ("YYYY-MM-DD", "YYYY-MM"), without Date parsing: a
// `new Date("2026-10-27")` is UTC midnight and shifts the day in Brazil's time zones.

const DATE = /^(\d{4})-(\d{2})-(\d{2})$/;
const MONTH = /^(\d{4})-(\d{2})$/;

function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}

/**
 * Age from a birth date, both "YYYY-MM-DD": "3 anos", "1 ano", "8 meses", "menos de 1 mês". A month
 * is complete on the same day number (born on the 31st: complete on the last day of shorter months
 * only from the next one, which is fine for a pet's age). Null when it cannot be computed.
 */
export function petAge(birthDate: string | null | undefined, today: string): string | null {
  const birth = dateParts(birthDate);
  const now = dateParts(today);
  if (!birth || !now) return null;
  let months = (now.year - birth.year) * 12 + (now.month - birth.month);
  if (now.day < birth.day) months -= 1;
  if (months < 0) return null;
  if (months >= 12) return plural(Math.floor(months / 12), "ano", "anos");
  if (months >= 1) return plural(months, "mês", "meses");
  return "menos de 1 mês";
}

function dateParts(value: string | null | undefined): { year: number; month: number; day: number } | null {
  const match = value?.match(DATE);
  return match ? { year: Number(match[1]), month: Number(match[2]), day: Number(match[3]) } : null;
}

/** "2026-10" for a valid month text; null otherwise (e.g. an edited URL). */
export function parseMonth(value: string | null | undefined): string | null {
  const match = value?.match(MONTH);
  if (!match) return null;
  const month = Number(match[2]);
  return month >= 1 && month <= 12 ? (value ?? null) : null;
}

/** "2026-10" moved by `delta` months: ("2026-01", -1) → "2025-12". */
export function shiftMonth(month: string, delta: number): string {
  const match = month.match(MONTH);
  if (!match) return month;
  const index = Number(match[1]) * 12 + Number(match[2]) - 1 + delta;
  const year = Math.floor(index / 12);
  return `${String(year).padStart(4, "0")}-${String((index % 12) + 1).padStart(2, "0")}`;
}

const monthName = new Intl.DateTimeFormat("pt-BR", { month: "long", year: "numeric", timeZone: "UTC" });

/** "2026-10" → "Outubro de 2026". */
export function formatMonthName(month: string): string {
  const match = month.match(MONTH);
  if (!match) return month;
  const text = monthName.format(new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, 1)));
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** Suggested due date for a new transaction of `month`: today in the current month, else its 1st day. */
export function defaultDayOf(month: string, today: string): string {
  return today.startsWith(month) ? today : `${month}-01`;
}

function toUtc(value: string): Date | null {
  const parts = dateParts(value);
  return parts ? new Date(Date.UTC(parts.year, parts.month - 1, parts.day)) : null;
}

function fromUtc(date: Date): string {
  const year = String(date.getUTCFullYear()).padStart(4, "0");
  const month = String(date.getUTCMonth() + 1).padStart(2, "0");
  const day = String(date.getUTCDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

/** "YYYY-MM-DD" for a valid date text; null otherwise (e.g. an edited URL with "2026-02-31"). */
export function parseDate(value: string | null | undefined): string | null {
  const date = value ? toUtc(value) : null;
  return date && fromUtc(date) === value ? value : null;
}

/** ("2026-10-31", 1) → "2026-11-01". Computed in UTC, so daylight saving never skips a day. */
export function addDays(value: string, days: number): string {
  const date = toUtc(value);
  if (!date) return value;
  date.setUTCDate(date.getUTCDate() + days);
  return fromUtc(date);
}

/** 0 = domingo ... 6 = sábado (same numbering as WEEKDAY_SHORT). */
export function weekdayOf(value: string): number {
  return toUtc(value)?.getUTCDay() ?? 0;
}

/**
 * Days of a month view: whole weeks from Sunday to Saturday, starting on the Sunday on or before the
 * 1st and ending on the Saturday on or after the last day (4 to 6 weeks).
 */
export function monthGridDays(month: string): string[] {
  const first = parseMonth(month) ? `${month}-01` : null;
  if (!first) return [];
  const last = addDays(`${shiftMonth(month, 1)}-01`, -1);
  const start = addDays(first, -weekdayOf(first));
  const end = addDays(last, 6 - weekdayOf(last));
  const days: string[] = [];
  for (let day = start; day <= end; day = addDays(day, 1)) days.push(day);
  return days;
}

const LONG_WEEKDAYS = ["Domingo", "Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado"] as const;

/** Day relative to `today`: "Hoje", "Amanhã", or weekday plus date ("Sexta, 07/11"). */
export function relativeDayLabel(value: string, today: string): string {
  if (value === today) return "Hoje";
  if (value === addDays(today, 1)) return "Amanhã";
  const parts = dateParts(value);
  if (!parts) return value;
  const day = String(parts.day).padStart(2, "0");
  const month = String(parts.month).padStart(2, "0");
  return `${LONG_WEEKDAYS[weekdayOf(value)]}, ${day}/${month}`;
}
