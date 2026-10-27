import { render, screen } from "@testing-library/react";
import { lazy, Suspense } from "react";
import { describe, expect, it, vi } from "vitest";
import { ErrorBoundary } from "./ErrorBoundary";

describe("ErrorBoundary", () => {
  it("keeps a lazy chunk that fails to load inside its block, with a reload button", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {}); // React and the boundary log the error
    const BrokenChart = lazy(() => Promise.reject(new Error("Failed to fetch dynamically imported module")));

    render(
      <>
        <ErrorBoundary>
          <Suspense fallback={<p>Carregando...</p>}>
            <BrokenChart />
          </Suspense>
        </ErrorBoundary>
        <section aria-label="Outro card">Afazeres</section>
      </>,
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("Não foi possível exibir esta parte");
    expect(screen.getByRole("button", { name: "Recarregar" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Outro card" })).toHaveTextContent("Afazeres");
  });
});
