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
