import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useLocation } from "react-router";
import { describe, expect, it } from "vitest";
import type { Transaction } from "@/api/types";
import { setToken } from "@/auth/token";
import { demoUser, jsonBody, jsonResponse, mockApi, pageOf, renderWithProviders, STAMP } from "@/test/utils";
import { FinancePage } from "./FinancePage";

const vet: Transaction = {
  id: "tx-1",
  type: "expense",
  amount: "220.00",
  category: "Pets",
  description: "Consulta veterinária",
  due_date: "2026-10-05",
  pet_id: null,
  paid_at: null,
  paid_on: null,
  overdue: true,
  created_at: STAMP,
  updated_at: STAMP,
};

function mockFinance(extra: Parameters<typeof mockApi>[0] = {}) {
  setToken("token");
  return mockApi({
    "GET /api/auth/me": () => jsonResponse(demoUser),
    "GET /api/transactions": () => jsonResponse(pageOf([vet])),
    "GET /api/transactions/categories": () => jsonResponse(["Pets"]),
    "GET /api/pets": () => jsonResponse(pageOf([])),
    "GET /api/budgets": () => jsonResponse([]),
    ...extra,
  });
}

function LocationProbe() {
  return <output data-testid="location">{useLocation().search}</output>;
}

describe("FinancePage", () => {
  it("'Pagar' sends paid_on and shows the 422 under the date", async () => {
    const requests = mockFinance({
      "POST /api/transactions/tx-1/pay": () =>
        jsonResponse(
          { detail: [{ type: "value_error", loc: ["body"], msg: "A data de pagamento não pode ser no futuro." }] },
          422,
        ),
    });
    renderWithProviders(<FinancePage />, "/financas?month=2026-10");
    const user = userEvent.setup();

    const row = (await screen.findByRole("button", { name: "Pagar Consulta veterinária" })).closest("li")!;
    expect(within(row).getByText("atrasada")).toBeInTheDocument();
    await user.click(within(row).getByRole("button", { name: "Pagar Consulta veterinária" }));

    const dialog = screen.getByRole("dialog", { name: "Registrar pagamento" });
    const date = within(dialog).getByLabelText(/Paga em/);
    await user.clear(date);
    await user.type(date, "2030-01-15");
    await user.click(within(dialog).getByRole("button", { name: "Pagar" }));

    expect(await within(dialog).findByText("A data de pagamento não pode ser no futuro.")).toBeInTheDocument();
    expect(date).toHaveAttribute("aria-invalid", "true");
    expect(jsonBody(requests.find((r) => r.method === "POST"))).toEqual({ paid_on: "2030-01-15" });
  });

  it("creating a transaction sends the amount as a decimal string", async () => {
    const requests = mockFinance({
      "POST /api/transactions": () => jsonResponse({ ...vet, id: "tx-2", amount: "12.90" }, 201),
    });
    renderWithProviders(<FinancePage />, "/financas?month=2026-10");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Nova transação" }));
    const dialog = screen.getByRole("dialog", { name: "Nova transação" });
    await user.type(within(dialog).getByLabelText(/Valor/), "12,9");
    await user.type(within(dialog).getByLabelText(/Categoria/), "Padaria");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await screen.findByText("Transação criada.")).toBeInTheDocument();
    expect(jsonBody(requests.find((r) => r.method === "POST"))).toMatchObject({
      type: "expense",
      amount: "12.90",
      category: "Padaria",
      paid_on: null,
    });
  });

  it("'Copiar do mês anterior' with nothing new says 'Nada a copiar'", async () => {
    const requests = mockFinance({
      "POST /api/budgets/copy": () => jsonResponse({ created: [], skipped: [] }, 200),
    });
    renderWithProviders(<FinancePage />, "/financas?tab=budgets&month=2026-01");
    const user = userEvent.setup();

    await screen.findByText("Nenhum orçamento em janeiro de 2026.");
    await user.click(screen.getByRole("button", { name: "Copiar do mês anterior" }));

    expect(await screen.findByText("Nada a copiar.")).toBeInTheDocument();
    expect(requests.find((r) => r.method === "POST")?.url).toBe("/api/budgets/copy?from=2025-12&to=2026-01");
  });

  it("changing the month updates the URL and the query", async () => {
    const requests = mockFinance();
    renderWithProviders(
      <>
        <FinancePage />
        <LocationProbe />
      </>,
      "/financas?month=2026-12&status=pending",
    );
    const user = userEvent.setup();

    expect(await screen.findByText("Dezembro de 2026")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Próximo mês" }));

    expect(screen.getByText("Janeiro de 2027")).toBeInTheDocument();
    expect(screen.getByTestId("location")).toHaveTextContent("month=2027-01");
    const listOf = (month: string) => requests.find((r) => r.url.startsWith("/api/transactions?") && r.url.includes(`month=${month}`));
    await waitFor(() => expect(listOf("2027-01")).toBeDefined());
    // The other filters stay.
    expect(listOf("2027-01")?.url).toContain("status=pending");
  });
});
