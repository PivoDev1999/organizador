import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";
import type { Pet, PetEvent } from "@/api/types";
import { setToken } from "@/auth/token";
import { demoUser, jsonResponse, mockApi, pageOf, renderWithProviders, STAMP } from "@/test/utils";
import { PetDetailPage } from "./PetDetailPage";

const PET_ID = "e148de11-4b69-4baf-9aaa-723c571afd13";

const mel: Pet = {
  id: PET_ID,
  name: "Mel",
  species: "Cachorro",
  breed: null,
  birth_date: null,
  weight_kg: null,
  notes: null,
  created_at: STAMP,
  updated_at: STAMP,
};

function event(id: string, type: PetEvent["type"], description: string): PetEvent {
  return { id, pet_id: PET_ID, type, occurred_on: "2026-10-01", next_due_on: null, description, created_at: STAMP, updated_at: STAMP };
}

const vaccine = event("ev-1", "vaccine", "V10");
const checkup = event("ev-2", "vet", "Consulta de rotina");

function renderDetail(path: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/pets/:id" element={<PetDetailPage />} />
    </Routes>,
    path,
  );
}

describe("PetDetailPage", () => {
  it("suggests descriptions from every event, even with the history filtered by type", async () => {
    setToken("token");
    mockApi({
      "GET /api/auth/me": () => jsonResponse(demoUser),
      [`GET /api/pets/${PET_ID}`]: () => jsonResponse(mel),
      // The history asks with type=vet; the suggestions ask without filters.
      [`GET /api/pets/${PET_ID}/events`]: ({ url }) =>
        jsonResponse(pageOf(url.includes("type=vet") ? [checkup] : [vaccine, checkup])),
      "GET /api/files": () => jsonResponse([]),
    });
    renderDetail(`/pets/${PET_ID}?type=vet`);
    const user = userEvent.setup();

    expect(await screen.findByText("Consulta de rotina")).toBeInTheDocument();
    expect(screen.queryByText("V10")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Novo evento" }));

    const dialog = screen.getByRole("dialog", { name: "Novo evento: Mel" });
    const listId = within(dialog).getByLabelText("Descrição").getAttribute("list");
    await waitFor(() => {
      const options = [...(document.getElementById(listId ?? "")?.querySelectorAll("option") ?? [])].map((o) => o.value);
      expect(options).toEqual(["Consulta de rotina", "V10"]);
    });
  });

  it("an id that is not a UUID shows 'Pet não encontrado' without calling the API", async () => {
    setToken("token");
    const requests = mockApi({ "GET /api/auth/me": () => jsonResponse(demoUser) });
    renderDetail("/pets/abc");

    expect(await screen.findByText("Pet não encontrado.")).toBeInTheDocument();
    expect(requests.filter((r) => r.url.startsWith("/api/pets"))).toEqual([]);
  });
});
