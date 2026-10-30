import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { SystemStatus } from "@/api/types";
import { setToken } from "@/auth/token";
import { demoUser, jsonResponse, mockApi, renderWithProviders } from "@/test/utils";
import { StatusPage } from "./StatusPage";

const status: SystemStatus = {
  overall: "degraded",
  version: "0.1.0+abc1234",
  server_time: "2026-10-29T13:30:00-03:00",
  timezone: "America/Sao_Paulo",
  uptime_seconds: 3 * 3600 + 5 * 60,
  database: { status: "ok", latency_ms: 1.8, alembic_revision: "b0e9e518b85c" },
  storage: { status: "ok", latency_ms: 4.2 },
  backup: {
    status: "stale",
    last_success_at: "2026-10-27T03:00:04-03:00",
    age_hours: 58.5,
    size_bytes: 41418,
    name: "2026-10-27_030000",
    max_age_hours: 26,
  },
};

describe("StatusPage", () => {
  it("shows every block and flags a stale backup", async () => {
    setToken("token");
    mockApi({
      "GET /api/auth/me": () => jsonResponse(demoUser),
      "GET /api/status": () => jsonResponse(status),
    });
    renderWithProviders(<StatusPage />, "/status");

    const summary = await screen.findByRole("region", { name: "Resumo" });
    expect(summary).toHaveTextContent("Funcionando, com avisos");
    expect(summary).toHaveTextContent("O último backup tem mais de 26 horas.");

    const app = screen.getByRole("region", { name: "Aplicação" });
    expect(app).toHaveTextContent("0.1.0+abc1234");
    expect(app).toHaveTextContent("29/10/2026, 13:30");
    expect(app).toHaveTextContent("3 h 5 min");
    expect(screen.getByRole("region", { name: "Banco de dados" })).toHaveTextContent("b0e9e518b85c");
    expect(screen.getByRole("region", { name: "Arquivos (Garage)" })).toHaveTextContent("funcionando");

    const backup = screen.getByRole("region", { name: "Último backup" });
    expect(within(backup).getByText("atrasado")).toBeInTheDocument();
    expect(backup).toHaveTextContent("27/10/2026, 03:00");
    expect(backup).toHaveTextContent("há 2 d 10 h");
    expect(backup).toHaveTextContent("40,4 KB");
  });

  it("shows the system as down when the API answers 503", async () => {
    setToken("token");
    mockApi({
      "GET /api/auth/me": () => jsonResponse(demoUser),
      "GET /api/status": () => jsonResponse({ detail: "API indisponível. Tente de novo em instantes." }, 503),
    });
    renderWithProviders(<StatusPage />, "/status");

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Sistema fora do ar");
    expect(alert).toHaveTextContent("Não foi possível falar com a API ou com o banco de dados.");
    expect(alert).toHaveTextContent("docker compose ps");
    expect(screen.getByRole("button", { name: "Atualizar" })).toBeEnabled();
  });
});
