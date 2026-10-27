import { ArrowLeft, Pencil, Receipt, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { errorMessage } from "@/api/errors";
import { Attachments } from "@/components/attachments/Attachments";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { PageHeader } from "@/components/PageHeader";
import { SkeletonList } from "@/components/Spinner";
import { useToday } from "@/hooks/useToday";
import { petAge } from "@/lib/calendar";
import { formatDate, formatQuantity } from "@/lib/format";
import { isNotFound } from "@/lib/formErrors";
import { isUuid } from "@/lib/uuid";
import { DeletePetDialog } from "./pets/DeletePetDialog";
import { PetEventsSection } from "./pets/PetEventsSection";
import { PetFormModal } from "./pets/PetFormModal";
import { usePet } from "./pets/queries";

const LINK_CLASS = "inline-flex min-h-11 items-center gap-1 rounded-lg px-2 font-medium text-brand-800 hover:bg-slate-100";

function BackLink() {
  return (
    <Link to="/pets" className={`${LINK_CLASS} mb-2 -ml-2`}>
      <ArrowLeft aria-hidden="true" className="size-4" />
      Pets
    </Link>
  );
}

function PetNotFound() {
  return (
    <>
      <BackLink />
      <Card>
        <EmptyState title="Pet não encontrado." description="Ele pode ter sido excluído em outro aparelho." />
      </Card>
    </>
  );
}

function Fact({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="py-2">
      <dt className="text-sm text-slate-700">{label}</dt>
      <dd className="break-words text-slate-900">{value || "—"}</dd>
    </div>
  );
}

/** One pet: its data, attachments and the history of events (with filters in the URL). */
export function PetDetailPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const today = useToday();
  // An id that is not a UUID (edited URL) cannot exist: no request, straight to "não encontrado".
  const validId = isUuid(id);
  const pet = usePet(id, validId);
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);

  if (!validId) return <PetNotFound />;
  if (pet.isPending) {
    return (
      <>
        <BackLink />
        <SkeletonList rows={4} label="Carregando o pet..." />
      </>
    );
  }
  if (pet.isError && isNotFound(pet.error)) return <PetNotFound />;
  if (pet.isError) {
    return (
      <>
        <BackLink />
        <Card>
          <ErrorState
            title="Não foi possível carregar o pet"
            message={errorMessage(pet.error)}
            onRetry={() => void pet.refetch()}
          />
        </Card>
      </>
    );
  }

  const data = pet.data;
  const birth = data.birth_date ? `${formatDate(data.birth_date)} (${petAge(data.birth_date, today) ?? "—"})` : null;
  return (
    <>
      <BackLink />
      <PageHeader
        title={data.name}
        description={[data.species, data.breed].filter(Boolean).join(" · ")}
        actions={
          <div className="flex flex-wrap gap-2">
            <Link to={`/financas?pet_id=${encodeURIComponent(data.id)}`} className={LINK_CLASS}>
              <Receipt aria-hidden="true" className="size-4" />
              Ver gastos
            </Link>
            <Button variant="secondary" onClick={() => setEditing(true)}>
              <Pencil aria-hidden="true" className="size-4" />
              Editar
            </Button>
            <Button variant="secondary" onClick={() => setDeleting(true)} className="text-red-700">
              <Trash2 aria-hidden="true" className="size-4" />
              Excluir
            </Button>
          </div>
        }
      />
      {/* Phone: data, history, attachments. Desktop: data and attachments on the left, history on the right. */}
      <div className="grid items-start gap-4 lg:grid-cols-3 lg:grid-rows-[auto_1fr]">
        <Card title="Dados">
          <dl className="divide-y divide-slate-100">
            <Fact label="Espécie" value={data.species} />
            <Fact label="Raça" value={data.breed} />
            <Fact label="Nascimento" value={birth} />
            <Fact label="Peso" value={data.weight_kg ? `${formatQuantity(data.weight_kg)} kg` : null} />
            <Fact label="Observações" value={data.notes} />
          </dl>
        </Card>
        <div className="lg:col-span-2 lg:col-start-2 lg:row-span-2 lg:row-start-1">
          <PetEventsSection pet={data} />
        </div>
        <Card className="lg:col-start-1">
          <Attachments entityType="pet" entityId={data.id} />
        </Card>
      </div>

      {editing && <PetFormModal pet={data} onClose={() => setEditing(false)} />}
      {deleting && (
        <DeletePetDialog pet={data} onClose={() => setDeleting(false)} onDeleted={() => void navigate("/pets", { replace: true })} />
      )}
    </>
  );
}
