import { apiFetch } from "./client";
import { fetchFirstPages } from "./pagination";
import type {
  Page,
  Pet,
  PetCreate,
  PetEvent,
  PetEventCreate,
  PetEventUpdate,
  PetReminder,
  PetUpdate,
  QueryParams,
} from "./types";

/** Filters of GET /api/pets, without pagination (the screen asks for pages). */
export type PetFilters = Omit<NonNullable<QueryParams<"/api/pets", "get">>, "limit" | "offset">;

/** Filters of GET /api/pets/{id}/events, without pagination. */
export type PetEventFilters = Omit<NonNullable<QueryParams<"/api/pets/{pet_id}/events", "get">>, "limit" | "offset">;

export const petKeys = {
  all: ["pets"] as const,
  lists: () => ["pets", "list"] as const,
  list: (filters: PetFilters, pages: number) => ["pets", "list", filters, pages] as const,
  /** Every pet by name, for selects (e.g. the transaction form). */
  options: () => ["pets", "options"] as const,
  detail: (id: string) => ["pets", "detail", id] as const,
  species: () => ["pets", "species"] as const,
  reminders: (within: number) => ["pets", "reminders", within] as const,
  events: (petId: string, filters: PetEventFilters, pages: number) => ["pets", "events", petId, filters, pages] as const,
  /** Descriptions already used by a pet, unfiltered (suggestions of the event form). */
  descriptions: (petId: string) => ["pets", "descriptions", petId] as const,
};

export function listPets(filters: PetFilters, pages: number): Promise<Page<Pet>> {
  return fetchFirstPages((limit, offset) => apiFetch("/api/pets", { query: { ...filters, limit, offset } }), pages);
}

/** Up to 100 pets by name (the API's page limit): plenty for a household. */
export function listPetOptions(): Promise<Page<Pet>> {
  return apiFetch("/api/pets", { query: { sort: "name", limit: 100 } });
}

export function getPet(id: string): Promise<Pet> {
  return apiFetch("/api/pets/{pet_id}", { params: { pet_id: id } });
}

export function listSpecies(): Promise<string[]> {
  return apiFetch("/api/pets/species");
}

export function listReminders(within: number): Promise<PetReminder[]> {
  return apiFetch("/api/pets/reminders", { query: { within } });
}

export function createPet(body: PetCreate): Promise<Pet> {
  return apiFetch("/api/pets", { method: "post", json: body });
}

export function updatePet(id: string, body: PetUpdate): Promise<Pet> {
  return apiFetch("/api/pets/{pet_id}", { method: "patch", params: { pet_id: id }, json: body });
}

/** Also deletes its events and attachments; transactions linked to it stay, without the pet. */
export function deletePet(id: string): Promise<undefined> {
  return apiFetch("/api/pets/{pet_id}", { method: "delete", params: { pet_id: id } });
}

export function listPetEvents(petId: string, filters: PetEventFilters, pages: number): Promise<Page<PetEvent>> {
  return fetchFirstPages(
    (limit, offset) =>
      apiFetch("/api/pets/{pet_id}/events", { params: { pet_id: petId }, query: { ...filters, limit, offset } }),
    pages,
  );
}

/** Latest 100 events of a pet without filters: source of the description suggestions. */
export function listRecentPetEvents(petId: string): Promise<Page<PetEvent>> {
  return apiFetch("/api/pets/{pet_id}/events", { params: { pet_id: petId }, query: { limit: 100 } });
}

export function createPetEvent(petId: string, body: PetEventCreate): Promise<PetEvent> {
  return apiFetch("/api/pets/{pet_id}/events", { method: "post", params: { pet_id: petId }, json: body });
}

export function updatePetEvent(petId: string, eventId: string, body: PetEventUpdate): Promise<PetEvent> {
  return apiFetch("/api/pets/{pet_id}/events/{event_id}", {
    method: "patch",
    params: { pet_id: petId, event_id: eventId },
    json: body,
  });
}

export function deletePetEvent(petId: string, eventId: string): Promise<undefined> {
  return apiFetch("/api/pets/{pet_id}/events/{event_id}", {
    method: "delete",
    params: { pet_id: petId, event_id: eventId },
  });
}
