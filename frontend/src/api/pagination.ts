import type { Page } from "./types";

/** Items per "Carregar mais". */
export const PAGE_SIZE = 20;
/** The API caps `limit` at 100 (PAGE_MAX_LIMIT in the backend). */
const API_MAX_LIMIT = 100;

/**
 * The first `pages` pages of a list as one page (offset 0). The screens keep how many pages are
 * shown in the URL, so a reload brings back the same items: one request while they fit in the API's
 * limit, more requests of up to 100 items after that.
 */
export async function fetchFirstPages<T>(
  fetchPage: (limit: number, offset: number) => Promise<Page<T>>,
  pages: number,
): Promise<Page<T>> {
  const wanted = Math.max(1, pages) * PAGE_SIZE;
  const first = await fetchPage(Math.min(wanted, API_MAX_LIMIT), 0);
  let items = first.items;
  while (items.length < wanted && items.length < first.total) {
    const next = await fetchPage(Math.min(wanted - items.length, API_MAX_LIMIT), items.length);
    if (next.items.length === 0) break;
    items = items.concat(next.items);
  }
  return { items, total: first.total, limit: wanted, offset: 0 };
}

/** Replaces one item (by id) in a cached page; other pages are returned untouched. */
export function replaceInPage<T extends { id: string }>(
  page: Page<T> | undefined,
  id: string,
  update: (item: T) => T,
): Page<T> | undefined {
  if (!page || !page.items.some((item) => item.id === id)) return page;
  return { ...page, items: page.items.map((item) => (item.id === id ? update(item) : item)) };
}
