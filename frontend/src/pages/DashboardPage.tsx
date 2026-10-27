import { ChartBar, Gauge, type LucideIcon } from "lucide-react";
import { lazy, Suspense, type ReactNode } from "react";
import { errorMessage } from "@/api/errors";
import { useAuth } from "@/auth/useAuth";
import { Card } from "@/components/Card";
import { ErrorBoundary, ReloadErrorState } from "@/components/ErrorBoundary";
import { ErrorState } from "@/components/ErrorState";
import { PageHeader } from "@/components/PageHeader";
import { SectionCard } from "@/components/SectionCard";
import { Skeleton } from "@/components/Spinner";
import { formatLongDate, monthOf } from "@/lib/format";
import { BillsCard } from "./dashboard/BillsCard";
import { MonthCard } from "./dashboard/MonthCard";
import { PantryCard } from "./dashboard/PantryCard";
import { PetsCard } from "./dashboard/PetsCard";
import { useDashboard } from "./dashboard/queries";
import { RoutinesCard } from "./dashboard/RoutinesCard";
import { ShoppingCard } from "./dashboard/ShoppingCard";
import { TasksCard } from "./dashboard/TasksCard";

// Recharts is most of the bundle: the charts load in their own chunk, so the cards show up first.
const CategoryChart = lazy(() => import("./dashboard/CategoryChart").then((m) => ({ default: m.CategoryChart })));
const BudgetChart = lazy(() => import("./dashboard/BudgetChart").then((m) => ({ default: m.BudgetChart })));

const GRID = "grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3";

function ChartFallback() {
  return (
    <div role="status">
      <span className="sr-only">Carregando o gráfico...</span>
      <Skeleton className="h-64 w-full rounded-xl" />
    </div>
  );
}

/** A lazy chart: its own loading placeholder, and a failed chunk stays inside its card. */
function ChartSlot({ title, icon, children }: { title: string; icon: LucideIcon; children: ReactNode }) {
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

function DashboardSkeleton() {
  return (
    <div role="status">
      <span className="sr-only">Carregando o painel...</span>
      <div className={GRID}>
        {Array.from({ length: 6 }, (_, index) => (
          <Skeleton key={index} className="h-48 w-full rounded-xl" />
        ))}
      </div>
    </div>
  );
}

export function DashboardPage() {
  const { user } = useAuth();
  const dashboard = useDashboard();
  const firstName = user?.name.trim().split(/\s+/)[0];
  const greeting = firstName ? `Olá, ${firstName}!` : "Olá!";
  const data = dashboard.data;

  return (
    <>
      <PageHeader
        title="Painel"
        description={
          data ? (
            <>
              {greeting} Hoje é <time dateTime={data.date}>{formatLongDate(data.date)}</time>.
            </>
          ) : (
            greeting
          )
        }
      />
      {dashboard.isPending && <DashboardSkeleton />}
      {dashboard.isError && !data && (
        <Card>
          <ErrorState
            title="Não foi possível carregar o painel"
            message={errorMessage(dashboard.error)}
            onRetry={() => void dashboard.refetch()}
          />
        </Card>
      )}
      {data && (
        <div className={GRID}>
          <TasksCard tasks={data.tasks} />
          <RoutinesCard routines={data.routines} />
          <BillsCard upcoming={data.finance.upcoming} />
          <MonthCard month={data.finance.month} />
          <ChartSlot title="Despesas por categoria" icon={ChartBar}>
            <CategoryChart month={monthOf(data.date)} />
          </ChartSlot>
          <ChartSlot title="Uso dos orçamentos" icon={Gauge}>
            <BudgetChart month={monthOf(data.date)} alerts={data.finance.budget_alerts} />
          </ChartSlot>
          <PantryCard pantry={data.pantry} />
          <ShoppingCard shopping={data.shopping} />
          <PetsCard pets={data.pets} />
        </div>
      )}
    </>
  );
}
