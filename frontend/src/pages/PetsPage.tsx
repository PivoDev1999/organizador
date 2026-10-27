import { Plus } from "lucide-react";
import { useState } from "react";
import type { Pet, PetReminder } from "@/api/types";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { PageHeader } from "@/components/PageHeader";
import { Tabs } from "@/components/Tabs";
import { useUrlFilters } from "@/hooks/useUrlFilters";
import { DeletePetDialog } from "./pets/DeletePetDialog";
import { PetEventFormModal } from "./pets/PetEventFormModal";
import { PetFormModal } from "./pets/PetFormModal";
import { PetsListTab } from "./pets/PetsListTab";
import { RemindersTab } from "./pets/RemindersTab";

type Tab = "pets" | "reminders";
const TABS = [
  { value: "pets", label: "Pets" },
  { value: "reminders", label: "Lembretes" },
] as const satisfies ReadonlyArray<{ value: Tab; label: string }>;

/** null: closed; "new": creating; a pet: editing. */
type Editing = Pet | "new" | null;

export function PetsPage() {
  const url = useUrlFilters();
  const tab = url.getEnum<Tab>("tab", ["pets", "reminders"], "pets");
  const [editing, setEditing] = useState<Editing>(null);
  const [deleting, setDeleting] = useState<Pet | null>(null);
  const [registering, setRegistering] = useState<PetReminder | null>(null);

  return (
    <>
      <PageHeader
        title="Pets"
        actions={
          <Button onClick={() => setEditing("new")}>
            <Plus aria-hidden="true" className="size-5" />
            Novo pet
          </Button>
        }
      />
      <Card>
        <Tabs
          label="Pets"
          tabs={TABS}
          value={tab}
          // Each tab has its own filters: switching drops the other's.
          onChange={(next) => url.update({ tab: next === "pets" ? null : next, species: null, q: null, within: null })}
        >
          {tab === "pets" ? (
            <PetsListTab onCreate={() => setEditing("new")} onEdit={setEditing} onDelete={setDeleting} />
          ) : (
            <RemindersTab onRegister={setRegistering} />
          )}
        </Tabs>
      </Card>

      {editing && <PetFormModal pet={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
      {deleting && <DeletePetDialog pet={deleting} onClose={() => setDeleting(null)} />}
      {registering && (
        <PetEventFormModal
          petId={registering.pet_id}
          petName={registering.pet_name}
          event={null}
          draft={{ type: registering.type, description: registering.description }}
          descriptions={registering.description ? [registering.description] : []}
          onClose={() => setRegistering(null)}
        />
      )}
    </>
  );
}
