import { BellRing, CalendarX, Clock, PackageMinus } from "lucide-react";
import { errorMessage } from "@/api/errors";
import { ALERTS_EXPIRING_WITHIN } from "@/api/pantry";
import { Card } from "@/components/Card";
import { ErrorState } from "@/components/ErrorState";
import { Skeleton } from "@/components/Spinner";
import { StatBadge } from "@/components/StatBadge";
import { usePantryAlerts } from "./queries";

/** Counters of GET /api/pantry/alerts at the top of the page. */
export function PantryAlertsCard() {
  const alerts = usePantryAlerts();

  let content;
  if (alerts.isPending) {
    content = (
      <div role="status">
        <span className="sr-only">Carregando alertas...</span>
        <Skeleton className="h-8 w-full" />
      </div>
    );
  } else if (alerts.isError) {
    content = (
      <ErrorState
        title="Não foi possível carregar os alertas"
        message={errorMessage(alerts.error)}
        onRetry={() => void alerts.refetch()}
      />
    );
  } else {
    const { low_stock: low, expired, expiring_soon: soon } = alerts.data;
    content =
      low.length + expired.length + soon.length === 0 ? (
        <p className="text-slate-700">Nada vencido, vencendo ou acabando.</p>
      ) : (
        <div className="flex flex-wrap gap-2">
          <StatBadge value={expired.length} label="vencidos" tone={expired.length ? "danger" : "neutral"} icon={CalendarX} />
          <StatBadge
            value={soon.length}
            label={`vencem em ${ALERTS_EXPIRING_WITHIN} dias`}
            tone={soon.length ? "warning" : "neutral"}
            icon={Clock}
          />
          <StatBadge value={low.length} label="com estoque baixo" tone={low.length ? "info" : "neutral"} icon={PackageMinus} />
        </div>
      );
  }

  return (
    <Card title="Alertas" icon={BellRing}>
      {content}
    </Card>
  );
}
