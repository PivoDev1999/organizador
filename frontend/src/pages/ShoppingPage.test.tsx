import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { ShoppingItem } from "@/api/types";
import { setToken } from "@/auth/token";
import { demoUser, jsonResponse, mockApi, pageOf, renderWithProviders, STAMP, type RecordedRequest } from "@/test/utils";
import { ShoppingPage } from "./ShoppingPage";

const rice: ShoppingItem = {
  id: "s1",
  name: "Arroz",
  category: "Grãos",
  quantity: "2.000",
  unit: "kg",
  estimated_price: "6.50",
  is_purchased: false,
  purchased_at: null,
  pantry_item_id: "p1",
  created_at: STAMP,
  updated_at: STAMP,
};

function setup(extra: Record<string, (request: RecordedRequest) => Response>) {
  setToken("token");
  const requests = mockApi({
    "GET /api/auth/me": () => jsonResponse(demoUser),
    "GET /api/shopping": () => jsonResponse(pageOf([rice])),
    "GET /api/shopping/summary": () => jsonResponse({ pending: 1, purchased: 0, estimated_total: "13.00" }),
    ...extra,
  });
  renderWithProviders(<ShoppingPage />, "/mercado");
  return requests;
}

describe("ShoppingPage", () => {
  it("buys an item and tells when the pantry was restocked", async () => {
    setup({
      "POST /api/shopping/s1/purchase": () =>
        jsonResponse({ ...rice, is_purchased: true, purchased_at: STAMP, pantry_restocked: true }),
    });
    const user = userEvent.setup();

    expect(await screen.findByRole("region", { name: "Grãos" })).toBeInTheDocument();
    expect(screen.getByText("R$ 13,00")).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: "Comprado: Arroz" }));

    expect(await screen.findByText("Despensa reposta: Arroz.")).toBeInTheDocument();
  });

  it("'Gerar da despensa' with 200 and [] says there is nothing to add", async () => {
    const requests = setup({ "POST /api/shopping/from-pantry": () => jsonResponse([], 200) });
    const user = userEvent.setup();

    await screen.findByText("Arroz");
    await user.click(screen.getByRole("checkbox", { name: "Incluir vencidos" }));
    await user.click(screen.getByRole("button", { name: "Gerar da despensa" }));

    expect(await screen.findByText(/Nada a adicionar/)).toBeInTheDocument();
    expect(requests.find((r) => r.method === "POST")?.url).toBe("/api/shopping/from-pantry?include_expired=true");
  });
});
