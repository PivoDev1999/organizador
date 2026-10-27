import { Button } from "./Button";

export interface LoadMoreProps {
  shown: number;
  total: number;
  loading: boolean;
  onLoadMore: () => void;
  /** False when no more pages can be shown (the screen's page cap): a hint replaces the button. */
  canLoadMore?: boolean;
}

/** "Mostrando X de Y" with a "Carregar mais" button while there are items left. */
export function LoadMore({ shown, total, loading, onLoadMore, canLoadMore = true }: LoadMoreProps) {
  if (total === 0) return null;
  return (
    <div className="mt-3 flex flex-col items-center gap-2 border-t border-slate-100 pt-3">
      <p className="text-sm text-slate-700" aria-live="polite">
        Mostrando {shown} de {total}
      </p>
      {shown < total && !canLoadMore && (
        <p className="text-sm text-slate-700">Use a busca ou os filtros para encontrar os demais.</p>
      )}
      {shown < total && canLoadMore && (
        <Button variant="secondary" size="sm" loading={loading} onClick={onLoadMore}>
          Carregar mais
        </Button>
      )}
    </div>
  );
}
