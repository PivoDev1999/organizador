import { describe, expect, it } from "vitest";
import { budgetLevel, compareDecimal, parseDecimalInput, toDecimalInput, toMoneyString, type BudgetLevel } from "./decimal";

describe("decimal", () => {
  it("compares decimal strings exactly and applies the backend's budget alert rule", () => {
    // Beyond float precision the two would be equal as numbers.
    expect(compareDecimal("9007199254740993.10", "9007199254740993.09")).toBe(1);
    expect(compareDecimal("1.5", "1.50")).toBe(0);
    expect(compareDecimal("-0.01", "0")).toBe(-1);

    const cases: Array<[spent: string, amount: string, level: BudgetLevel]> = [
      ["79.99", "100.00", "normal"],
      ["80.00", "100.00", "warning"],
      ["100.00", "100.00", "warning"], // exactly 100% still warns
      ["100.01", "100.00", "exceeded"],
      ["0.01", "0.00", "exceeded"], // any spending on a zero budget
      ["0.00", "0.00", "normal"],
      ["10004.99", "10000.00", "exceeded"], // shown as 100.0%, but above the budget
    ];
    for (const [spent, amount, level] of cases) expect(budgetLevel(spent, amount), `${spent}/${amount}`).toBe(level);
  });

  it("turns the price typed by the user into the API's money string, without floats", () => {
    const cases: Array<[typed: string, sent: string | null]> = [
      ["12,90", "12.90"],
      ["12,9", "12.90"],
      ["12.90", "12.90"], // a dot without a comma (and not 3 digits after it) is the decimal separator
      [",5", "0.50"], // empty integer part
      [" 7 ", "7.00"],
      ["0,05", "0.05"],
      ["1.234,56", "1234.56"], // dots group thousands when there is a comma
      ["9007199254740993,10", "9007199254740993.10"], // beyond float precision
      ["12,", "12.00"],
      ["12,999", null], // more than 2 decimals
      ["1.234", null], // ambiguous in pt-BR: refused, asks for a comma
      ["1 2", null], // spaces only trimmed at the ends
      ["12.34,5", null], // malformed thousands
      ["1,2,3", null],
      ["-5", null],
      ["abc", null],
      ["", null],
    ];
    for (const [typed, sent] of cases) expect(toMoneyString(typed), JSON.stringify(typed)).toBe(sent);
    expect(parseDecimalInput("1.500", 3).error).toBe("Use vírgula para decimais (ex.: 1,5).");
    // Prefilled values from the API come back in pt-BR, so editing keeps working.
    expect(parseDecimalInput(toDecimalInput("1.500"), 3).value).toBe("1.5");
    expect(toMoneyString(toDecimalInput("1234.50", true))).toBe("1234.50");
  });
});
