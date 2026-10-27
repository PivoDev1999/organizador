// Exact arithmetic on the decimal strings of the API ("12.90", "-3.5"): BigInt over a shared scale,
// never floats. Only what the screens need: compare, add, sign.

const DECIMAL = /^(-)?(\d+)(?:\.(\d+))?$/;

export interface ParsedDecimal {
  negative: boolean;
  /** Integer digits, as sent ("0012" stays "0012"). */
  integer: string;
  /** Fraction digits, as sent ("" when there is no dot). */
  fraction: string;
}

/** Splits a decimal string ("-12.90") into sign and digits; null if it is not one. Shared with format.ts. */
export function parseDecimal(value: string | null | undefined): ParsedDecimal | null {
  const match = value?.trim().match(DECIMAL);
  if (!match) return null;
  const [, minus, integer = "0", fraction = ""] = match;
  return { negative: minus === "-", integer, fraction };
}

type Parsed = ParsedDecimal;

function parse(value: string): Parsed {
  const parsed = parseDecimal(value);
  // The message never carries the value (project rule: errors may reach the user).
  if (!parsed) throw new Error("Invalid decimal string");
  return parsed;
}

/** The value times 10^scale as a BigInt (`scale` must be ≥ the number of fraction digits). */
function scaled({ negative, integer, fraction }: Parsed, scale: number): bigint {
  const units = BigInt(integer + fraction.padEnd(scale, "0"));
  return negative ? -units : units;
}

function commonScale(values: Parsed[]): number {
  return Math.max(0, ...values.map((value) => value.fraction.length));
}

/** -1, 0 or 1, like a sort comparator. "1.50" and "1.5" are equal. */
export function compareDecimal(a: string, b: string): -1 | 0 | 1 {
  const pa = parse(a);
  const pb = parse(b);
  const scale = commonScale([pa, pb]);
  const diff = scaled(pa, scale) - scaled(pb, scale);
  return diff === 0n ? 0 : diff < 0n ? -1 : 1;
}

export function isNegative(value: string): boolean {
  return compareDecimal(value, "0") < 0;
}

/** Exact sum, with as many fraction digits as the longest input (at least 2: money). */
export function sumDecimals(values: readonly string[]): string {
  const parsed = values.map(parse);
  const scale = Math.max(2, commonScale(parsed));
  const total = parsed.reduce((sum, value) => sum + scaled(value, scale), 0n);
  const digits = (total < 0n ? -total : total).toString().padStart(scale + 1, "0");
  const integer = digits.slice(0, digits.length - scale);
  return `${total < 0n ? "-" : ""}${integer}.${digits.slice(digits.length - scale)}`;
}

export type BudgetLevel = "normal" | "warning" | "exceeded";

/**
 * Same rule as the backend (`budget_alert_level` in app/core/finance.py), on the exact values:
 * exceeded when spent > amount; warning when spent > 0 and spent ≥ 80% of amount (up to exactly
 * 100%); normal otherwise. A zero budget with any spending is exceeded.
 */
export function budgetLevel(spent: string, amount: string): BudgetLevel {
  const ps = parse(spent);
  const pa = parse(amount);
  const scale = commonScale([ps, pa]);
  const s = scaled(ps, scale);
  const a = scaled(pa, scale);
  if (s > a) return "exceeded";
  // spent * 100 >= 80 * amount  <=>  5 * spent >= 4 * amount
  if (s > 0n && 5n * s >= 4n * a) return "warning";
  return "normal";
}

export const DECIMAL_COMMA_MESSAGE = "Use vírgula para decimais (ex.: 1,5).";

/**
 * What the user typed → decimal string for the API, or why it is not accepted, as text only (no
 * floats). pt-BR: the comma is the decimal separator and dots group thousands ("1.234,5" → "1234.5",
 * ",5" → "0.5"). Without a comma, a dot followed by exactly 3 digits ("1.234") is ambiguous (a
 * thousand in pt-BR, or 1.234?) and is refused with DECIMAL_COMMA_MESSAGE; other dots are decimal
 * separators ("12.90"). Only the ends are trimmed: "1 2" is invalid. The API still validates range,
 * zero, etc.
 */
export function parseDecimalInput(
  raw: string,
  maxPlaces: number,
): { value: string; error: null } | { value: null; error: string } {
  const invalid = { value: null, error: "Informe um número, como 2 ou 0,5." } as const;
  const text = raw.trim();
  if (!text) return invalid;
  let normalized: string;
  if (text.includes(",")) {
    if (text.indexOf(",") !== text.lastIndexOf(",")) return invalid;
    const [integer = "", fraction = ""] = text.split(",");
    // Thousands groups only in the canonical shape: "1.234.567".
    if (integer.includes(".") && !/^\d{1,3}(\.\d{3})+$/.test(integer)) return invalid;
    normalized = `${integer.replace(/\./g, "") || "0"}.${fraction}`;
  } else {
    if (/^\d+\.\d{3}$/.test(text)) return { value: null, error: DECIMAL_COMMA_MESSAGE };
    normalized = text;
  }
  const match = normalized.match(/^(\d+)(?:\.(\d*))?$/);
  if (!match) return invalid;
  const [, integer = "", fraction = ""] = match;
  if (fraction.length > maxPlaces) {
    return { value: null, error: `Use no máximo ${maxPlaces} casas decimais.` };
  }
  return { value: fraction ? `${integer}.${fraction}` : integer, error: null };
}

/** `parseDecimalInput` when only the value matters: null if it is not accepted. */
export function normalizeDecimalInput(raw: string, maxPlaces: number): string | null {
  return parseDecimalInput(raw, maxPlaces).value;
}

/** API decimal ("1.500", "12.90") → what a pt-BR user types back ("1,5", or "12,90" with `keepZeros`). */
export function toDecimalInput(value: string | null | undefined, keepZeros = false): string {
  if (!value) return "";
  const [integer = "", fraction = ""] = value.split(".");
  const shown = keepZeros ? fraction : fraction.replace(/0+$/, "");
  return shown ? `${integer},${shown}` : integer;
}

/** Money typed by the user → "12.90" (always 2 decimals, as the API's Money expects). Null if invalid. */
export function toMoneyString(raw: string): string | null {
  const value = normalizeDecimalInput(raw, 2);
  if (value === null) return null;
  const [integer, fraction = ""] = value.split(".");
  return `${integer}.${fraction.padEnd(2, "0")}`;
}
