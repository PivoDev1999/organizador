import { History } from "lucide-react";
import { useId } from "react";
import { errorMessage } from "@/api/errors";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { LoadMore } from "@/components/LoadMore";
import { SkeletonList } from "@/components/Spinner";
import { formatDate } from "@/lib/format";
import { useRoutineLogs } from "./queries";

/** Days the routine was done, newest first, with "Carregar mais". */
export function RoutineHistory({ routineId }: { routineId: string }) {
  const headingId = useId();
  const logs = useRoutineLogs(routineId);

  let content;
  if (logs.isPending) {
    content = <SkeletonList rows={2} label="Carregando o histórico..." />;
  } else if (logs.isError) {
    content = (
      <ErrorState
        title="Não foi possível carregar o histórico"
        message={errorMessage(logs.error)}
        onRetry={() => void logs.refetch()}
      />
    );
  } else {
    const items = logs.data.pages.flatMap((page) => page.items);
    const total = logs.data.pages[0]?.total ?? 0;
    content =
      items.length === 0 ? (
        <EmptyState icon={History} title="Ainda não foi feita." />
      ) : (
        <>
          <ul className="divide-y divide-slate-100">
            {items.map((log) => (
              <li key={log.id} className="py-2">
                <time dateTime={log.done_on} className="text-slate-900">
                  {formatDate(log.done_on)}
                </time>
                {log.note && <p className="text-sm text-slate-700">{log.note}</p>}
              </li>
            ))}
          </ul>
          <LoadMore
            shown={items.length}
            total={total}
            loading={logs.isFetchingNextPage}
            onLoadMore={() => void logs.fetchNextPage()}
          />
        </>
      );
  }

  return (
    <section aria-labelledby={headingId} className="space-y-3">
      <h2 id={headingId} className="text-lg font-semibold">
        Histórico
      </h2>
      {content}
    </section>
  );
}
