import { describe, expect, it } from "vitest";
import type { CategoryTotals } from "@/api/types";
import { prepareCategoryData } from "./chartData";

const NBSP = " ";

const expense = (category: string, total: string): CategoryTotals => ({
  type: "expense",
  category,
  total,
  paid: total,
  pending: "0.00",
});

describe("prepareCategoryData", () => {
  it("keeps the 6 largest expenses in order and sums the rest exactly into 'Outras'", () => {
    const data = prepareCategoryData([
      { ...expense("Salário", "5000.00"), type: "income" }, // incomes are left out
      expense("Lazer", "0.10"),
      expense("Mercado", "800.00"),
      expense("Casa", "1200.50"),
      expense("Saúde", "300.00"),
      expense("Pets", "250.00"),
      expense("Transporte", "300.00"),
      expense("Educação", "90.00"),
      expense("Assinaturas", "0.20"),
      expense("Zerada", "0.00"), // nothing spent: no bar
    ]);

    expect(data.map((item) => item.category)).toEqual([
      "Casa",
      "Mercado",
      "Saúde", // tie with Transporte: by name
      "Transporte",
      "Pets",
      "Educação",
      "Outras",
    ]);
    // 0.10 + 0.20 is 0.30000000000000004 in floats; the label comes from the exact string.
    expect(data.at(-1)).toMatchObject({ total: "0.30", label: `R$${NBSP}0,30` });
    expect(data[0]).toMatchObject({ total: "1200.50", label: `R$${NBSP}1.200,50`, value: 1200.5 });
  });
});
