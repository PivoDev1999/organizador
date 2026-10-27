import { describe, expect, it } from "vitest";
import { petAge } from "./calendar";

describe("petAge", () => {
  it.each([
    ["2023-10-27", "3 anos"],
    ["2025-10-27", "1 ano"],
    ["2025-10-28", "11 meses"],
    ["2026-02-27", "8 meses"],
    ["2026-09-27", "1 mês"],
    ["2026-10-01", "menos de 1 mês"],
    ["2026-10-28", null],
    [null, null],
  ])("born %s, on 2026-10-27: %s", (birth, expected) => {
    expect(petAge(birth, "2026-10-27")).toBe(expected);
  });
});
