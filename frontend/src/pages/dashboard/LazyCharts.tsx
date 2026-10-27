import type { LucideIcon } from "lucide-react";
import { lazy, Suspense, type ReactNode } from "react";
import { ErrorBoundary, ReloadErrorState } from "@/components/ErrorBoundary";
import { SectionCard } from "@/components/SectionCard";
import { Skeleton } from "@/components/Spinner";

// Recharts is most of the bundle: the charts load in their own chunk, so the cards show up first.
// Shared by the dashboard and the finance screen.
export const CategoryChart = lazy(() => import("./CategoryChart").then((m) => ({ default: m.CategoryChart })));
export const BudgetChart = lazy(() => import("./BudgetChart").then((m) => ({ default: m.BudgetChart })));

function ChartFallback() {
  return (
    <div role="status">
      <span className="sr-only">Carregando o gráfico...</span>
      <Skeleton className="h-64 w-full rounded-xl" />
    </div>
  );
}

/** A lazy chart: its own loading placeholder, and a failed chunk stays inside its card. */
export function ChartSlot({ title, icon, children }: { title: string; icon: LucideIcon; children: ReactNode }) {
  return (
    <ErrorBoundary
      fallback={
        <SectionCard title={title} icon={icon}>
          <ReloadErrorState title="Não foi possível carregar o gráfico" />
        </SectionCard>
      }
    >
      <Suspense fallback={<ChartFallback />}>{children}</Suspense>
    </ErrorBoundary>
  );
}
