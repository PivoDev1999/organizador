import type { PetEventType } from "@/api/types";

export const PET_EVENT_TYPE_LABELS: Record<PetEventType, string> = {
  vaccine: "Vacina",
  vet: "Veterinário",
  medication: "Remédio",
  grooming: "Banho e tosa",
  other: "Outro",
};
