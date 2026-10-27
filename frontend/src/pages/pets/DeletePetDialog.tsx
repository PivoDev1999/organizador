import type { Pet } from "@/api/types";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { useDeletePet } from "./queries";

export interface DeletePetDialogProps {
  pet: Pet;
  onClose: () => void;
  /** After a successful delete (e.g. the detail page goes back to the list). */
  onDeleted?: () => void;
}

/** The API deletes the events and attachments too; transactions stay in Finanças without the pet. */
export function DeletePetDialog({ pet, onClose, onDeleted }: DeletePetDialogProps) {
  const remove = useDeletePet();
  return (
    <ConfirmDialog
      title="Excluir pet?"
      message={`"${pet.name}" e os anexos serão excluídos. Os eventos também serão apagados e os gastos em Finanças continuam, sem o vínculo.`}
      loading={remove.isPending}
      onConfirm={() =>
        remove.mutate(pet, {
          onSuccess: () => onDeleted?.(),
          onSettled: () => onClose(),
        })
      }
      onCancel={onClose}
    />
  );
}
