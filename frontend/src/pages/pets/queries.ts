import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { dashboardKeys } from "@/api/dashboard";
import { errorMessage } from "@/api/errors";
import { financeKeys } from "@/api/finance";
import {
  createPet,
  createPetEvent,
  deletePet,
  deletePetEvent,
  getPet,
  listPetEvents,
  listPetOptions,
  listPets,
  listRecentPetEvents,
  listReminders,
  listSpecies,
  petKeys,
  updatePet,
  updatePetEvent,
  type PetEventFilters,
  type PetFilters,
} from "@/api/pets";
import type { Pet, PetCreate, PetEvent, PetEventCreate, PetEventUpdate, PetUpdate } from "@/api/types";
import { useToast } from "@/components/toast/useToast";
import { isNotFound } from "@/lib/formErrors";

/** Window of the reminders tab, in days. */
export const REMINDER_WINDOWS = [7, 30, 90] as const;
export const DEFAULT_REMINDER_WINDOW = 30;

export function usePets(filters: PetFilters, pages: number) {
  return useQuery({
    queryKey: petKeys.list(filters, pages),
    queryFn: () => listPets(filters, pages),
    placeholderData: keepPreviousData,
  });
}

export function usePetOptions() {
  return useQuery({ queryKey: petKeys.options(), queryFn: listPetOptions });
}

/** `enabled` false (e.g. an id that is not a UUID) skips the request. */
export function usePet(id: string, enabled = true) {
  return useQuery({ queryKey: petKeys.detail(id), queryFn: () => getPet(id), enabled });
}

export function useSpecies() {
  return useQuery({ queryKey: petKeys.species(), queryFn: listSpecies });
}

export function useReminders(within: number) {
  return useQuery({ queryKey: petKeys.reminders(within), queryFn: () => listReminders(within) });
}

export function usePetEvents(petId: string, filters: PetEventFilters, pages: number) {
  return useQuery({
    queryKey: petKeys.events(petId, filters, pages),
    queryFn: () => listPetEvents(petId, filters, pages),
    placeholderData: keepPreviousData,
  });
}

/** Distinct descriptions, ignoring case and outer spaces (as the reminders group a series). */
export function distinctDescriptions(events: readonly PetEvent[]): string[] {
  const seen = new Map<string, string>();
  for (const event of events) {
    const text = event.description?.trim();
    if (text && !seen.has(text.toLowerCase())) seen.set(text.toLowerCase(), text);
  }
  return [...seen.values()].sort((a, b) => a.localeCompare(b, "pt-BR"));
}

/**
 * Descriptions used by the pet, for the event form's datalist. Own query without the screen's
 * filters and pagination (a "vet" filter must not hide the "V10" series); fetched only while the
 * form is open.
 */
export function usePetEventDescriptions(petId: string, enabled: boolean) {
  return useQuery({
    queryKey: petKeys.descriptions(petId),
    queryFn: () => listRecentPetEvents(petId),
    select: (page) => distinctDescriptions(page.items),
    enabled,
  });
}

/**
 * Pets, events and reminders share the "pets" prefix; the dashboard shows the reminders. With
 * `finance`, the transaction lists and summaries too (a deleted pet leaves its expenses without it).
 */
function useRefreshPets() {
  const queryClient = useQueryClient();
  return (finance = false) =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: petKeys.all }),
      queryClient.invalidateQueries({ queryKey: dashboardKeys.all }),
      finance && queryClient.invalidateQueries({ queryKey: financeKeys.transactions }),
      finance && queryClient.invalidateQueries({ queryKey: financeKeys.budgetsAll }),
    ]);
}

export function useSavePet(pet: Pet | null) {
  const refresh = useRefreshPets();
  return useMutation({
    mutationFn: (body: PetCreate & PetUpdate) => (pet ? updatePet(pet.id, body) : createPet(body)),
    onSuccess: () => refresh(),
    // Deleted on another device: the form closes and the list drops it.
    onError: (error) => (isNotFound(error) ? refresh() : undefined),
  });
}

export function useDeletePet() {
  const refresh = useRefreshPets();
  const toast = useToast();
  return useMutation({
    mutationFn: (pet: Pet) => deletePet(pet.id),
    onSuccess: () => toast.success("Pet excluído."),
    onError: (error) => toast.error(errorMessage(error)),
    // Not awaited: the detail page navigates away on success instead of waiting for its own pet to
    // be refetched (a 404 that would flash "não encontrado" before leaving).
    onSettled: () => {
      void refresh(true);
    },
  });
}

export function useSavePetEvent(petId: string, event: PetEvent | null) {
  const refresh = useRefreshPets();
  return useMutation({
    mutationFn: (body: PetEventCreate & PetEventUpdate) =>
      event ? updatePetEvent(petId, event.id, body) : createPetEvent(petId, body),
    onSuccess: () => refresh(),
    onError: (error) => (isNotFound(error) ? refresh() : undefined),
  });
}

export function useDeletePetEvent() {
  const refresh = useRefreshPets();
  const toast = useToast();
  return useMutation({
    mutationFn: (event: PetEvent) => deletePetEvent(event.pet_id, event.id),
    onSuccess: () => toast.success("Evento excluído."),
    onError: (error) => toast.error(errorMessage(error)),
    onSettled: () => refresh(),
  });
}
