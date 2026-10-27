import { describe, expect, it } from "vitest";
import { budgetLevel, compareDecimal, type BudgetLevel } from "./decimal";

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
});
