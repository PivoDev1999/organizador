import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router";
import { vi } from "vitest";
import { createQueryClient } from "@/api/queryClient";
import { AppProviders } from "@/AppProviders";

export interface RecordedRequest {
  method: string;
  url: string;
  headers: Headers;
  body: BodyInit | null | undefined;
}

type Handler = (request: RecordedRequest) => Response | Promise<Response>;

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

/**
 * Replaces fetch with a table of handlers keyed by "METHOD /path" (query string ignored).
 * Unmatched requests fail the test with a 500. Returns the requests seen, in order.
 */
export function mockApi(handlers: Record<string, Handler>): RecordedRequest[] {
  const requests: RecordedRequest[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
      const url = String(input);
      const request: RecordedRequest = {
        method: (init.method ?? "GET").toUpperCase(),
        url,
        headers: new Headers(init.headers),
        body: init.body,
      };
      requests.push(request);
      const handler = handlers[`${request.method} ${url.split("?")[0]}`];
      return handler ? handler(request) : jsonResponse({ detail: `No mock for ${request.method} ${url}` }, 500);
    }),
  );
  return requests;
}

/** Renders `ui` with the app providers (fresh query client without retries) at `path`. */
export function renderWithProviders(ui: ReactElement, path = "/") {
  const client = createQueryClient();
  client.setDefaultOptions({ queries: { retry: false, staleTime: 0 }, mutations: { retry: false } });
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppProviders client={client}>{ui}</AppProviders>
    </MemoryRouter>,
  );
}

export const demoUser = {
  id: "11111111-1111-4111-8111-111111111111",
  email: "demo@organizador.local",
  name: "Demo",
  is_active: true,
  created_at: "2026-10-01T12:00:00Z",
};
