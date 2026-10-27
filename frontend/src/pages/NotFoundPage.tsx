import { SearchX } from "lucide-react";
import { Link } from "react-router";
import { Card } from "@/components/Card";
import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";

export function NotFoundPage() {
  return (
    <>
      <PageHeader title="Página não encontrada" />
      <Card>
        <EmptyState
          icon={SearchX}
          title="Este endereço não existe."
          action={
            <Link to="/" className="font-medium text-brand-700 underline underline-offset-2">
              Voltar ao painel
            </Link>
          }
        />
      </Card>
    </>
  );
}
