import { Construction } from "lucide-react";
import { Card } from "@/components/Card";
import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";

/** Temporary page for modules whose screens come in the next deliveries. */
export function PlaceholderPage({ title }: { title: string }) {
  return (
    <>
      <PageHeader title={title} />
      <Card>
        <EmptyState icon={Construction} title="Em construção" description="Esta tela chega nas próximas entregas." />
      </Card>
    </>
  );
}
