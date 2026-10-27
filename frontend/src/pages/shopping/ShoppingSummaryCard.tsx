import { CircleCheck, ListChecks, Receipt } from "lucide-react";
import { errorMessage } from "@/api/errors";
import { Card } from "@/components/Card";
import { ErrorState } from "@/components/ErrorState";
import { Skeleton } from "@/components/Spinner";
import { StatBadge } from "@/components/StatBadge";
import { formatMoney } from "@/lib/format";
import { useShoppingSummary } from "./queries";

export function ShoppingSummaryCard() {
  const summary = useShoppingSummary();

  let content;
  if (summary.isPending) {
    content = (
      <div role="status">
        <span className="sr-only">Carregando o resumo...</span>
        <Skeleton className="h-8 w-full" />
      </div>
    );
  } else if (summary.isError) {
    content = (
      <ErrorState
        title="Não foi possível carregar o resumo"
        message={errorMessage(summary.error)}
        onRetry={() => void summary.refetch()}
      />
    );
  } else {
    content = (
      <div className="flex flex-wrap gap-2">
        <StatBadge value={summary.data.pending} label="pendentes" tone="info" icon={ListChecks} />
        <StatBadge value={summary.data.purchased} label="comprados" icon={CircleCheck} />
        <StatBadge value={formatMoney(summary.data.estimated_total)} label="estimado" tone="success" icon={Receipt} />
      </div>
    );
  }

  return (
    <Card title="Resumo" icon={Receipt}>
      {content}
    </Card>
  );
}
