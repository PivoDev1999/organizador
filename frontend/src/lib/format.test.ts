import { describe, expect, it } from "vitest";
import { formatDate, formatDateTime, formatMoney, formatQuantity } from "./format";

const NBSP = " ";

describe("format", () => {
  it("formats money and quantities from decimal strings without going through floats", () => {
    const money: Array<[string | null, string]> = [
      ["12.90", `R$${NBSP}12,90`],
      ["0.1", `R$${NBSP}0,10`],
      ["-1234567.05", `-R$${NBSP}1.234.567,05`],
      ["-0.00", `R$${NBSP}0,00`],
      // Beyond float precision: 9007199254740993 would become ...992 as a number.
      ["9007199254740993.10", `R$${NBSP}9.007.199.254.740.993,10`],
      ["abc", "—"],
      [null, "—"],
    ];
    for (const [input, expected] of money) expect(formatMoney(input), String(input)).toBe(expected);

    const quantities: Array<[string, string]> = [
      ["1.500", "1,5"],
      ["2.000", "2"],
      ["1234.250", "1.234,25"],
      ["0.125", "0,125"],
    ];
    for (const [input, expected] of quantities) expect(formatQuantity(input), input).toBe(expected);
  });

  it("formats dates without time zone shifts and timestamps in the given zone", () => {
    const dates: Array<[string | null, string]> = [
      ["2026-10-27", "27/10/2026"],
      ["2026-01-01", "01/01/2026"],
      ["27/10/2026", "—"],
      [null, "—"],
    ];
    for (const [input, expected] of dates) expect(formatDate(input), String(input)).toBe(expected);

    // 01:30 UTC is still the previous day in São Paulo (UTC-3).
    expect(formatDateTime("2026-10-27T01:30:00Z", "America/Sao_Paulo")).toBe("26/10/2026, 22:30");
    expect(formatDateTime("2026-10-27T13:05:00+00:00", "UTC")).toBe("27/10/2026, 13:05");
    expect(formatDateTime("not a date")).toBe("—");
  });
});
