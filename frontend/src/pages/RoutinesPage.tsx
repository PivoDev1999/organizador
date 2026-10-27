import { Plus } from "lucide-react";
import { useState } from "react";
import type { Routine } from "@/api/types";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { PageHeader } from "@/components/PageHeader";
import { Tabs } from "@/components/Tabs";
import { useUrlFilters } from "@/hooks/useUrlFilters";
import { AllTab } from "./routines/AllTab";
import { useDeleteRoutine } from "./routines/queries";
import { RoutineFormModal } from "./routines/RoutineFormModal";
import { TodayTab } from "./routines/TodayTab";

type Tab = "today" | "all";
const TABS = [
  { value: "today", label: "Hoje" },
  { value: "all", label: "Todas" },
] as const satisfies ReadonlyArray<{ value: Tab; label: string }>;

/** null: closed; "new": creating; a routine: editing. */
type Editing = Routine | "new" | null;

export function RoutinesPage() {
  const url = useUrlFilters();
  const tab = url.getEnum<Tab>("tab", ["today", "all"], "today");
  const [editing, setEditing] = useState<Editing>(null);
  const [deleting, setDeleting] = useState<Routine | null>(null);
  const remove = useDeleteRoutine();

  return (
    <>
      <PageHeader
        title="Rotina"
        actions={
          <Button onClick={() => setEditing("new")}>
            <Plus aria-hidden="true" className="size-5" />
            Nova rotina
          </Button>
        }
      />
      <Card>
        <Tabs
          label="Rotinas"
          tabs={TABS}
          value={tab}
          // Switching tabs drops the filters of "Todas" (they only make sense there).
          onChange={(next) => url.update({ tab: next === "today" ? null : next, frequency: null, is_active: null, q: null })}
        >
          {tab === "today" ? (
            <TodayTab onOpen={setEditing} />
          ) : (
            <AllTab onOpen={setEditing} onCreate={() => setEditing("new")} onDelete={setDeleting} />
          )}
        </Tabs>
      </Card>

      {editing && <RoutineFormModal routine={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
      {deleting && (
        <ConfirmDialog
          title="Excluir rotina?"
          message={`"${deleting.name}", o histórico e os anexos dela serão excluídos.`}
          loading={remove.isPending}
          onConfirm={() => remove.mutate(deleting, { onSettled: () => setDeleting(null) })}
          onCancel={() => setDeleting(null)}
        />
      )}
    </>
  );
}
