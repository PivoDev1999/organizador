import { useCallback } from "react";
import { useSearchParams } from "react-router";

/** URL parameter with how many pages of the list are shown ("Carregar mais"). */
const PAGES_PARAM = "pages";
const MAX_PAGES = 10;

export type UrlValue = string | readonly string[] | boolean | null | undefined;

/**
 * Filters and pagination of a list kept in the URL, so they survive a reload and the back button.
 * Changes replace the current history entry (typing a search does not pile up entries). Any filter
 * change goes back to the first page.
 */
export function useUrlFilters() {
  const [params, setParams] = useSearchParams();

  const update = useCallback(
    (changes: Record<string, UrlValue>) => {
      setParams(
        (current) => {
          const next = new URLSearchParams(current);
          for (const [key, value] of Object.entries(changes)) {
            next.delete(key);
            if (Array.isArray(value)) value.forEach((item: string) => next.append(key, item));
            else if (value === true) next.set(key, "true");
            else if (typeof value === "string" && value !== "") next.set(key, value);
          }
          if (!(PAGES_PARAM in changes)) next.delete(PAGES_PARAM);
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );

  const pagesValue = Number(params.get(PAGES_PARAM));
  const pages = Number.isInteger(pagesValue) && pagesValue > 1 ? Math.min(pagesValue, MAX_PAGES) : 1;

  return {
    params,
    update,
    pages,
    /** False at the page cap: past it, the filters are the way to find older items. */
    canLoadMore: pages < MAX_PAGES,
    loadMore: () => update({ [PAGES_PARAM]: String(Math.min(pages + 1, MAX_PAGES)) }),
    /** Values of a repeated parameter that belong to `allowed` (unknown values from an edited URL are dropped). */
    getEnumList: <T extends string>(key: string, allowed: readonly T[]): T[] =>
      params.getAll(key).filter((value): value is T => (allowed as readonly string[]).includes(value)),
    getEnum: <T extends string>(key: string, allowed: readonly T[], fallback: T): T => {
      const value = params.get(key);
      return value !== null && (allowed as readonly string[]).includes(value) ? (value as T) : fallback;
    },
    getFlag: (key: string): boolean => params.get(key) === "true",
    getText: (key: string): string => params.get(key) ?? "",
  };
}
