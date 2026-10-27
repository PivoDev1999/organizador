import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { RoutineToday } from "@/api/types";
import { setToken } from "@/auth/token";
import { demoUser, jsonBody, jsonResponse, mockApi, pageOf, renderWithProviders, STAMP } from "@/test/utils";
import { RoutinesPage } from "./RoutinesPage";

const routine: RoutineToday = {
  id: "r1",
  name: "Regar plantas",
  description: null,
  frequency: "daily",
  days_of_week: null,
  day_of_month: null,
  time_of_day: "07:30:00",
  is_active: true,
  created_at: STAMP,
  updated_at: STAMP,
  done_today: true,
};

describe("RoutinesPage", () => {
  it("sends days_of_week for a weekly routine and clears the day of the month of the previous frequency", async () => {
    setToken("token");
    const requests = mockApi({
      "GET /api/auth/me": () => jsonResponse(demoUser),
      "GET /api/routines": () => jsonResponse(pageOf([])),
      "POST /api/routines": () => jsonResponse({ ...routine, frequency: "weekly", days_of_week: [1, 3] }, 201),
    });
    renderWithProviders(<RoutinesPage />, "/rotina?tab=all");
    const user = userEvent.setup();

    await screen.findByText("Nenhuma rotina ainda.");
    await user.click(screen.getAllByRole("button", { name: "Nova rotina" })[0]!);
    const dialog = screen.getByRole("dialog", { name: "Nova rotina" });
    await user.type(within(dialog).getByLabelText(/Nome/), "Lixo reciclável");

    await user.selectOptions(within(dialog).getByLabelText("Frequência"), "monthly");
    const dayOfMonth = within(dialog).getByLabelText(/Dia do mês/);
    expect(dayOfMonth).toHaveAccessibleDescription("Nos meses mais curtos, cai no último dia.");
    await user.type(dayOfMonth, "15");

    await user.selectOptions(within(dialog).getByLabelText("Frequência"), "weekly");
    expect(within(dialog).queryByLabelText(/Dia do mês/)).not.toBeInTheDocument();
    await user.click(within(dialog).getByRole("checkbox", { name: "quarta" }));
    await user.click(within(dialog).getByRole("checkbox", { name: "segunda" }));
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await screen.findByText("Rotina criada.")).toBeInTheDocument();
    expect(jsonBody(requests.find((r) => r.method === "POST"))).toEqual({
      name: "Lixo reciclável",
      description: null,
      frequency: "weekly",
      days_of_week: [1, 3],
      day_of_month: null,
      time_of_day: null,
      is_active: true,
    });
  });

  it("undoes today's mark by deleting the date of the latest log (the server's today)", async () => {
    setToken("token");
    let doneToday = true;
    const requests = mockApi({
      "GET /api/auth/me": () => jsonResponse(demoUser),
      "GET /api/routines/today": () => jsonResponse([{ ...routine, done_today: doneToday }]),
      "GET /api/routines/r1/logs": () =>
        jsonResponse(pageOf([{ id: "l1", routine_id: "r1", done_on: "2026-10-27", note: null, created_at: STAMP }])),
      "DELETE /api/routines/r1/logs/2026-10-27": () => {
        doneToday = false;
        return new Response(null, { status: 204 });
      },
    });
    renderWithProviders(<RoutinesPage />, "/rotina");
    const user = userEvent.setup();

    const checkbox = await screen.findByRole("checkbox", { name: "Feita hoje: Regar plantas" });
    expect(screen.getByText("1 de 1 feitas")).toBeInTheDocument();
    await user.click(checkbox);

    expect(checkbox).not.toBeChecked();
    expect(screen.getByText("0 de 1 feitas")).toBeInTheDocument();
    await waitFor(() =>
      expect(requests.find((r) => r.method === "DELETE")?.url).toBe("/api/routines/r1/logs/2026-10-27"),
    );
    expect(requests.find((r) => r.url.startsWith("/api/routines/r1/logs?"))?.url).toBe("/api/routines/r1/logs?limit=1");
  });

  it("does not delete any log when the fresh /today says the routine is no longer done (stale screen)", async () => {
    setToken("token");
    let todayCalls = 0;
    const requests = mockApi({
      "GET /api/auth/me": () => jsonResponse(demoUser),
      // Screen loaded before midnight (done); by the time of the undo the server's today says not done.
      "GET /api/routines/today": () => jsonResponse([{ ...routine, done_today: ++todayCalls === 1 }]),
      // Yesterday's log: it must survive.
      "GET /api/routines/r1/logs": () =>
        jsonResponse(pageOf([{ id: "l0", routine_id: "r1", done_on: "2026-10-26", note: null, created_at: STAMP }])),
    });
    renderWithProviders(<RoutinesPage />, "/rotina");
    const user = userEvent.setup();

    const checkbox = await screen.findByRole("checkbox", { name: "Feita hoje: Regar plantas" });
    await user.click(checkbox);

    await waitFor(() => expect(todayCalls).toBeGreaterThanOrEqual(3)); // load, undo check, refetch
    expect(checkbox).not.toBeChecked();
    expect(screen.getByText("0 de 1 feitas")).toBeInTheDocument();
    expect(requests.some((r) => r.method === "DELETE" || r.url.startsWith("/api/routines/r1/logs"))).toBe(false);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
