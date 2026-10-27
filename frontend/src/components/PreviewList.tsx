import type { ReactNode } from "react";

export interface PreviewListProps<T> {
  items: readonly T[];
  /** How many exist in total (the API sends only the first ones in `items`). */
  total: number;
  getKey: (item: T) => string;
  renderItem: (item: T) => ReactNode;
  /** Show at most this many of `items`. */
  max?: number;
  /** Screen reader text for the "+N" line, e.g. (n) => `e mais ${n} tarefas`. */
  moreLabel: (hidden: number) => string;
}

/** First items of a list plus a "+N" line for the rest. */
export function PreviewList<T>({ items, total, getKey, renderItem, max, moreLabel }: PreviewListProps<T>) {
  const shown = max === undefined ? items : items.slice(0, max);
  const hidden = Math.max(0, total - shown.length);
  if (shown.length === 0 && hidden === 0) return null;
  return (
    <ul className="divide-y divide-slate-100">
      {shown.map((item) => (
        <li key={getKey(item)} className="py-2">
          {renderItem(item)}
        </li>
      ))}
      {hidden > 0 && (
        <li className="py-2 text-sm font-medium text-slate-700">
          <span aria-hidden="true">+{hidden}</span>
          <span className="sr-only">{moreLabel(hidden)}</span>
        </li>
      )}
    </ul>
  );
}
