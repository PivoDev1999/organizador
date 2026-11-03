import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { AgendaEvent, CalendarItem } from "@/api/types";
import { setToken } from "@/auth/token";
import { demoUser, jsonBody, jsonResponse, mockApi, renderWithProviders, STAMP } from "@/test/utils";
import { AgendaPage } from "./AgendaPage";

// November 2026 starts on a Sunday and ends on a Monday: the grid goes from 01/11 to 05/12.
const PATH = "/agenda?month=2026-11&day=2026-11-10";

const dentist: AgendaEvent = {
  id: "e1",
  title: "Dentista",
  description: null,
  location: "Clínica Sorriso",
  starts_on: "2026-11-10",
  start_time: "14:30:00",
  end_time: "15:30:00",
  recurrence: "weekly",
  repeat_until: null,
  created_at: STAMP,
  updated_at: STAMP,
};

const items: CalendarItem[] = [
  {
    kind: "event",
    id: "e1",
    date: "2026-11-10",
    title: "Dentista",
    time: "14:30:00",
    end_time: "15:30:00",
    location: "Clínica Sorriso",
    recurrence: "weekly",
  },
  { kind: "task", id: "t1", date: "2026-11-10", title: "Trocar filtro", time: null, status: "todo", priority: "high" },
  {
    kind: "pet",
    id: "pe1",
    date: "2026-11-10",
    title: "Rex",
    time: null,
    pet_id: "p1",
    pet_name: "Rex",
    type: "vaccine",
    description: "V10",
  },
  { kind: "bill", id: "b1", date: "2026-11-15", title: "Internet", time: null, amount: "120.00", category: "Casa" },
];

function setup(extra: Parameters<typeof mockApi>[0] = {}) {
  setToken("token");
  const requests = mockApi({
    "GET /api/auth/me": () => jsonResponse(demoUser),
    "GET /api/calendar": () => jsonResponse(items),
    "GET /api/events/e1": () => jsonResponse(dentist),
    "GET /api/files": () => jsonResponse([]),
    ...extra,
  });
  renderWithProviders(<AgendaPage />, PATH);
  return { requests, user: userEvent.setup() };
}

async function openNewEvent(user: ReturnType<typeof userEvent.setup>) {
  await screen.findByRole("link", { name: "Trocar filtro" });
  await user.click(screen.getAllByRole("button", { name: "Novo compromisso" })[0]!);
  return screen.getByRole("dialog", { name: "Novo compromisso" });
}

describe("AgendaPage", () => {
  it("marks the days of the grid and lists the selected day, linking read-only items to their modules", async () => {
    const { requests, user } = setup();

    const day10 = await screen.findByRole("button", {
      name: "terça-feira, 10 de novembro de 2026: 1 compromisso, 1 tarefa, 1 lembrete de pet",
    });
    expect(day10).toHaveAttribute("aria-pressed", "true");
    expect(requests.find((r) => r.url.startsWith("/api/calendar"))?.url).toBe(
      "/api/calendar?from=2026-11-01&to=2026-12-05",
    );

    const day = screen.getByRole("region", { name: /10 de novembro/ });
    expect(within(day).getByText("14:30–15:30")).toBeInTheDocument();
    expect(within(day).getByRole("button", { name: "Dentista" })).toBeInTheDocument();
    expect(within(day).getByText("Clínica Sorriso")).toBeInTheDocument();
    expect(within(day).getByText("Repete toda semana")).toBeInTheDocument();
    expect(within(day).getByRole("link", { name: "Trocar filtro" })).toHaveAttribute("href", "/tarefas?q=Trocar+filtro");
    expect(within(day).getByRole("link", { name: "Rex" })).toHaveAttribute("href", "/pets/p1");
    expect(within(day).getByText("Tarefa")).toBeInTheDocument();
    expect(within(day).getAllByText("Dia inteiro")).toHaveLength(2);

    await user.click(screen.getByRole("button", { name: "domingo, 15 de novembro de 2026: 1 conta" }));
    const day15 = screen.getByRole("region", { name: /15 de novembro/ });
    expect(within(day15).getByRole("link", { name: "Internet" })).toHaveAttribute("href", "/financas?month=2026-11");
    expect(within(day15).getByText("R$ 120,00 · Casa")).toBeInTheDocument();
  });

  it("creates an all-day event on the selected day without times and refreshes the calendar", async () => {
    const { requests, user } = setup({ "POST /api/events": () => jsonResponse(dentist, 201) });
    const dialog = await openNewEvent(user);

    expect(within(dialog).getByLabelText(/^Data/)).toHaveValue("2026-11-10");
    expect(within(dialog).getByRole("checkbox", { name: "Dia inteiro" })).toBeChecked();
    // A time typed before checking "Dia inteiro" again is not sent.
    await user.click(within(dialog).getByRole("checkbox", { name: "Dia inteiro" }));
    await user.type(within(dialog).getByLabelText(/Início/), "09:00");
    await user.click(within(dialog).getByRole("checkbox", { name: "Dia inteiro" }));
    expect(within(dialog).queryByLabelText(/Início/)).not.toBeInTheDocument();
    await user.type(within(dialog).getByLabelText(/Título/), "Aniversário da Ana");
    await user.type(within(dialog).getByLabelText("Local"), " Casa da vó ");
    const calendarLoads = requests.filter((r) => r.url.startsWith("/api/calendar")).length;
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await screen.findByText("Compromisso criado.")).toBeInTheDocument();
    expect(jsonBody(requests.find((r) => r.method === "POST"))).toEqual({
      title: "Aniversário da Ana",
      description: null,
      location: "Casa da vó",
      starts_on: "2026-11-10",
      start_time: null,
      end_time: null,
      recurrence: "none",
      repeat_until: null,
    });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(requests.filter((r) => r.url.startsWith("/api/calendar")).length).toBeGreaterThan(calendarLoads);
  });

  it("refuses an end time that is not after the start", async () => {
    const { requests, user } = setup();
    const dialog = await openNewEvent(user);

    await user.type(within(dialog).getByLabelText(/Título/), "Reunião do condomínio");
    await user.click(within(dialog).getByRole("checkbox", { name: "Dia inteiro" }));
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));
    expect(await within(dialog).findByText("Informe o horário de início.")).toBeInTheDocument();

    await user.type(within(dialog).getByLabelText(/Início/), "15:00");
    await user.type(within(dialog).getByLabelText(/Fim/), "14:00");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    const end = within(dialog).getByLabelText(/Fim/);
    expect(await within(dialog).findByText("O fim deve ser depois do início.")).toBeInTheDocument();
    expect(end).toHaveAttribute("aria-invalid", "true");
    expect(requests.some((r) => r.method === "POST")).toBe(false);
  });

  it("shows 'Repetir até' only for repeating events and checks it against the date", async () => {
    const { requests, user } = setup({ "POST /api/events": () => jsonResponse(dentist, 201) });
    const dialog = await openNewEvent(user);

    await user.type(within(dialog).getByLabelText(/Título/), "Aula de inglês");
    expect(within(dialog).queryByLabelText(/Repetir até/)).not.toBeInTheDocument();
    await user.selectOptions(within(dialog).getByLabelText(/Repetição/), "weekly");
    const until = within(dialog).getByLabelText(/Repetir até/);
    await user.type(until, "2026-11-01");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));
    expect(await within(dialog).findByText("Deve ser no mesmo dia ou depois da data do compromisso.")).toBeInTheDocument();

    await user.clear(until);
    await user.type(until, "2026-12-15");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await screen.findByText("Compromisso criado.")).toBeInTheDocument();
    expect(jsonBody(requests.find((r) => r.method === "POST"))).toMatchObject({
      recurrence: "weekly",
      repeat_until: "2026-12-15",
    });
  });

  it("edits a repeating event with a warning and shows the API's rule errors under the field", async () => {
    const { requests, user } = setup({
      "PATCH /api/events/e1": () =>
        jsonResponse(
          {
            detail: [
              {
                type: "value_error",
                loc: ["body"],
                msg: "O horário de término (end_time) deve ser depois do horário de início (start_time).",
              },
            ],
          },
          422,
        ),
    });

    await user.click(await screen.findByRole("button", { name: "Dentista" }));
    const dialog = await screen.findByRole("dialog", { name: "Editar compromisso" });
    expect(await within(dialog).findByLabelText(/Início/)).toHaveValue("14:30");
    expect(within(dialog).getByText(/as alterações valem para todas as repetições/)).toBeInTheDocument();
    expect(within(dialog).getByRole("checkbox", { name: "Dia inteiro" })).not.toBeChecked();

    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    const end = within(dialog).getByLabelText(/Fim/);
    expect(await within(dialog).findByText(/deve ser depois do horário de início/)).toBeInTheDocument();
    expect(end).toHaveAttribute("aria-invalid", "true");
    expect(jsonBody(requests.find((r) => r.method === "PATCH"))).toMatchObject({
      start_time: "14:30",
      end_time: "15:30",
      recurrence: "weekly",
    });
  });

  it("opens the form with the event as the API has it now, never a cached copy", async () => {
    let stored = dentist;
    const { user } = setup({ "GET /api/events/e1": () => jsonResponse(stored) });

    await user.click(await screen.findByRole("button", { name: "Dentista" }));
    let dialog = await screen.findByRole("dialog", { name: "Editar compromisso" });
    expect(await within(dialog).findByLabelText(/Título/)).toHaveValue("Dentista");
    await user.click(within(dialog).getByRole("button", { name: "Cancelar" }));

    // Changed elsewhere (another tab or device) while the first copy is still in the cache.
    stored = { ...dentist, title: "Dentista (remarcado)", start_time: "16:00:00", end_time: null };
    await user.click(screen.getByRole("button", { name: "Dentista" }));
    dialog = await screen.findByRole("dialog", { name: "Editar compromisso" });
    expect(await within(dialog).findByLabelText(/Título/)).toHaveValue("Dentista (remarcado)");
    expect(within(dialog).getByLabelText(/Início/)).toHaveValue("16:00");
  });

  it("asks before deleting and warns that every repetition goes", async () => {
    const { requests, user } = setup({ "DELETE /api/events/e1": () => new Response(null, { status: 204 }) });

    await user.click(await screen.findByRole("button", { name: "Excluir Dentista" }));
    const dialog = screen.getByRole("dialog", { name: "Excluir compromisso?" });
    expect(dialog).toHaveTextContent("Este compromisso se repete: todas as repetições serão excluídas.");
    await user.click(within(dialog).getByRole("button", { name: "Excluir" }));

    expect(await screen.findByText("Compromisso excluído.")).toBeInTheDocument();
    expect(requests.some((r) => r.method === "DELETE" && r.url === "/api/events/e1")).toBe(true);
  });
});
