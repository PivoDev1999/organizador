// Display formatters (pt-BR). Money and quantities arrive from the API as decimal strings
// ("12.90", "1.500") and are formatted as text, never through a float.
import { parseDecimal } from "./decimal";

const PLACEHOLDER = "—";
const NBSP = "\u00a0";
const integerFormat = new Intl.NumberFormat("pt-BR");

/** Groups thousands of an integer string ("1234567" → "1.234.567"). BigInt keeps it exact. */
function groupThousands(digits: string): string {
  return integerFormat.format(BigInt(digits));
}

/** "12.90" → "R$ 12,90"; "-1234.5" → "-R$ 1.234,50". The space is a no-break space (U+00A0). */
export function formatMoney(value: string | null | undefined): string {
  const parsed = parseDecimal(value);
  if (!parsed) return PLACEHOLDER;
  const { negative, integer, fraction } = parsed;
  const cents = fraction.padEnd(2, "0").slice(0, 2);
  const isZero = /^0+$/.test(integer) && /^0+$/.test(cents);
  return `${negative && !isZero ? "-" : ""}R$${NBSP}${groupThousands(integer)},${cents}`;
}

/** "1.500" → "1,5"; "2.000" → "2"; "1234.250" → "1.234,25". */
export function formatQuantity(value: string | null | undefined): string {
  const parsed = parseDecimal(value);
  if (!parsed) return PLACEHOLDER;
  const { negative, integer, fraction } = parsed;
  const decimals = fraction.replace(/0+$/, "");
  const isZero = /^0+$/.test(integer) && decimals === "";
  return `${negative && !isZero ? "-" : ""}${groupThousands(integer)}${decimals ? `,${decimals}` : ""}`;
}

/** "2026-10-27" → "27/10/2026", by text: `new Date("2026-10-27")` is UTC midnight and shifts the day. */
export function formatDate(value: string | null | undefined): string {
  const match = value?.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return PLACEHOLDER;
  const [, year, month, day] = match;
  return `${day}/${month}/${year}`;
}

/** "2026-10-27" → "terça-feira, 27 de outubro". The date is read as UTC and formatted in UTC, so the
 * device's time zone never shifts the day. */
export function formatLongDate(value: string | null | undefined): string {
  const match = value?.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return PLACEHOLDER;
  const [, year, month, day] = match;
  const date = new Date(Date.UTC(Number(year), Number(month) - 1, Number(day)));
  return new Intl.DateTimeFormat("pt-BR", { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" }).format(
    date,
  );
}

/** "2026-10-27" → "2026-10" (the month parameter of the finance endpoints). */
export function monthOf(value: string): string {
  return value.slice(0, 7);
}

/** "85.50" → "85,5%"; null (no base to compare) → "—". */
export function formatPercent(value: string | null | undefined): string {
  const formatted = formatQuantity(value);
  return formatted === PLACEHOLDER ? PLACEHOLDER : `${formatted}%`;
}

/** ISO timestamp → "27/10/2026, 14:30" in the device's time zone (or `timeZone`, for tests). */
export function formatDateTime(value: string | null | undefined, timeZone?: string): string {
  if (!value) return PLACEHOLDER;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return PLACEHOLDER;
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone,
  }).format(date);
}

/** 1536 → "1,5 KB". Sizes are integers of bytes, so a number is fine here. */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let size = bytes / 1024;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size.toLocaleString("pt-BR", { maximumFractionDigits: 1 })} ${units[unit]}`;
}

/** Seconds → "menos de 1 min", "42 min", "3 h 5 min", "2 d 4 h". Whole units, rounded down. */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds) || seconds < 0) return PLACEHOLDER;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 1) return "menos de 1 min";
  const hours = Math.floor(minutes / 60);
  if (hours < 1) return `${minutes} min`;
  const days = Math.floor(hours / 24);
  if (days < 1) return minutes % 60 ? `${hours} h ${minutes % 60} min` : `${hours} h`;
  return hours % 24 ? `${days} d ${hours % 24} h` : `${days} d`;
}
