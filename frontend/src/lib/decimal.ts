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
