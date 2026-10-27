import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Pet, PetReminder } from "@/api/types";
import { setToken } from "@/auth/token";
import { localToday } from "@/lib/today";
import { demoUser, jsonBody, jsonResponse, mockApi, pageOf, renderWithProviders, STAMP } from "@/test/utils";
import { PetsPage } from "./PetsPage";

const mel: Pet = {
  id: "pet-1",
  name: "Mel",
  species: "Cachorro",
  breed: "Vira-lata",
  birth_date: "2022-05-10",
  weight_kg: "12.50",
  notes: null,
  created_at: STAMP,
  updated_at: STAMP,
};

const reminder: PetReminder = {
  event_id: "ev-1",
  pet_id: "pet-1",
  pet_name: "Mel",
  type: "vaccine",
  description: "V10",
  occurred_on: "2025-10-01",
  next_due_on: "2026-10-01",
  overdue: true,
};

function mockPets(extra: Parameters<typeof mockApi>[0] = {}) {
  setToken("token");
  return mockApi({
    "GET /api/auth/me": () => jsonResponse(demoUser),
    "GET /api/pets": () => jsonResponse(pageOf([mel])),
    "GET /api/pets/species": () => jsonResponse(["Cachorro"]),
    "GET /api/pets/reminders": () => jsonResponse([reminder]),
    ...extra,
  });
}

describe("PetsPage", () => {
  it("'Registrar agora' opens a new event with the reminder's type and description, dated today", async () => {
    const requests = mockPets({
      "POST /api/pets/pet-1/events": () =>
        jsonResponse({ ...reminder, id: "ev-2", occurred_on: localToday(), next_due_on: null, created_at: STAMP, updated_at: STAMP }, 201),
    });
    renderWithProviders(<PetsPage />, "/pets?tab=reminders");
    const user = userEvent.setup();

    const row = (await screen.findByRole("button", { name: /Registrar agora: Vacina V10 de Mel/ })).closest("li")!;
    expect(within(row).getByText("atrasado")).toBeInTheDocument();
    await user.click(within(row).getByRole("button", { name: /Registrar agora/ }));

    const dialog = screen.getByRole("dialog", { name: "Novo evento: Mel" });
    expect(within(dialog).getByLabelText("Tipo")).toHaveValue("vaccine");
    expect(within(dialog).getByLabelText("Descrição")).toHaveValue("V10");
    expect(within(dialog).getByLabelText(/^Data/)).toHaveValue(localToday());
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await screen.findByText("Evento registrado.")).toBeInTheDocument();
    expect(jsonBody(requests.find((r) => r.method === "POST"))).toEqual({
      type: "vaccine",
      occurred_on: localToday(),
      next_due_on: null,
      description: "V10",
    });
  });

  it("deleting a pet warns that events go and expenses stay without the link", async () => {
    const requests = mockPets({ "DELETE /api/pets/pet-1": () => new Response(null, { status: 204 }) });
    renderWithProviders(<PetsPage />, "/pets");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Excluir Mel" }));
    const dialog = screen.getByRole("dialog", { name: "Excluir pet?" });
    expect(dialog).toHaveTextContent(
      "Os eventos também serão apagados e os gastos em Finanças continuam, sem o vínculo.",
    );
    await user.click(within(dialog).getByRole("button", { name: "Excluir" }));

    expect(await screen.findByText("Pet excluído.")).toBeInTheDocument();
    expect(requests.some((r) => r.method === "DELETE" && r.url === "/api/pets/pet-1")).toBe(true);
  });
});
