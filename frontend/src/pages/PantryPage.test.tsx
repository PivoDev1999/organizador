import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { PantryItem } from "@/api/types";
import { setToken } from "@/auth/token";
import { demoUser, jsonBody, jsonResponse, mockApi, pageOf, renderWithProviders, STAMP } from "@/test/utils";
import { PantryPage } from "./PantryPage";

const rice: PantryItem = {
  id: "p1",
  name: "Arroz",
  category: "Grãos",
  quantity: "1.000",
  unit: "kg",
  min_quantity: "2.000",
  expires_on: null,
  location: "Armário",
  low_stock: true,
  expired: false,
  created_at: STAMP,
  updated_at: STAMP,
};

describe("PantryPage", () => {
  it("on 'Consumir' with 409 shows the toast and keeps the quantity", async () => {
    setToken("token");
    const requests = mockApi({
      "GET /api/auth/me": () => jsonResponse(demoUser),
      "GET /api/pantry": () => jsonResponse(pageOf([rice])),
      "GET /api/pantry/alerts": () => jsonResponse({ low_stock: [rice], expired: [], expiring_soon: [] }),
      "GET /api/pantry/categories": () => jsonResponse(["Grãos"]),
      "GET /api/pantry/locations": () => jsonResponse(["Armário"]),
      "POST /api/pantry/p1/consume": () => jsonResponse({ detail: "Quantidade insuficiente." }, 409),
    });
    renderWithProviders(<PantryPage />, "/despensa");
    const user = userEvent.setup();

    const row = (await screen.findByRole("button", { name: "Consumir Arroz" })).closest("li")!;
    expect(within(row).getByText("1 kg")).toBeInTheDocument();
    expect(within(row).getByText("estoque baixo")).toBeInTheDocument();

    await user.click(within(row).getByRole("button", { name: "Consumir Arroz" }));
    const dialog = screen.getByRole("dialog", { name: "Consumir: Arroz" });
    await user.type(within(dialog).getByLabelText(/Quantidade/), "1,5");
    await user.click(within(dialog).getByRole("button", { name: "Consumir" }));

    expect(await screen.findByText("Quantidade insuficiente.")).toBeInTheDocument();
    expect(jsonBody(requests.find((r) => r.method === "POST"))).toEqual({ amount: "1.5" });
    expect(within(row).getByText("1 kg")).toBeInTheDocument();
  });
});
