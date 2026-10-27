import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Task } from "@/api/types";
import { setToken } from "@/auth/token";
import { demoUser, jsonBody, jsonResponse, mockApi, pageOf, renderWithProviders, STAMP } from "@/test/utils";
import { TasksPage } from "./TasksPage";

const task: Task = {
  id: "t1",
  title: "Pagar IPTU",
  description: null,
  status: "todo",
  priority: "high",
  due_date: "2000-01-10", // before any "today": overdue while not done
  completed_at: null,
  created_at: STAMP,
  updated_at: STAMP,
};

describe("TasksPage", () => {
  it("marks a task as done at once and rolls it back when the request fails", async () => {
    setToken("token");
    let release: (response: Response) => void = () => {};
    const requests = mockApi({
      "GET /api/auth/me": () => jsonResponse(demoUser),
      "GET /api/tasks": () => jsonResponse(pageOf([task])),
      "PATCH /api/tasks/t1": () => new Promise<Response>((resolve) => (release = resolve)),
    });
    renderWithProviders(<TasksPage />, "/tarefas");
    const user = userEvent.setup();

    const checkbox = await screen.findByRole("checkbox", { name: "Concluída: Pagar IPTU" });
    expect(screen.getByText("atrasada")).toBeInTheDocument();

    await user.click(checkbox);
    expect(checkbox).toBeChecked(); // before the API answers
    expect(screen.queryByText("atrasada")).not.toBeInTheDocument(); // done tasks are never overdue
    expect(jsonBody(requests.find((r) => r.method === "PATCH"))).toEqual({ status: "done" });

    release(jsonResponse({ detail: "Erro interno." }, 500));

    expect(await screen.findByText("Erro interno.")).toBeInTheDocument();
    expect(checkbox).not.toBeChecked();
    expect(screen.getByText("atrasada")).toBeInTheDocument();
  });

  it("shows a 422 under the title field and a rule error at the top of the form", async () => {
    setToken("token");
    const requests = mockApi({
      "GET /api/auth/me": () => jsonResponse(demoUser),
      "GET /api/tasks": () => jsonResponse(pageOf([task])),
      "POST /api/tasks": () =>
        jsonResponse(
          {
            detail: [
              { type: "value_error", loc: ["body", "title"], msg: "O título deve ter no máximo 200 caracteres." },
              { type: "value_error", loc: ["body"], msg: "Regra de negócio violada." },
            ],
          },
          422,
        ),
    });
    renderWithProviders(<TasksPage />, "/tarefas");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Nova tarefa" }));
    const dialog = screen.getByRole("dialog", { name: "Nova tarefa" });
    await user.type(within(dialog).getByLabelText(/Título/), "Comprar lâmpadas");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    const title = within(dialog).getByLabelText(/Título/);
    expect(await within(dialog).findByText("O título deve ter no máximo 200 caracteres.")).toBeInTheDocument();
    expect(title).toHaveAccessibleDescription("O título deve ter no máximo 200 caracteres.");
    expect(title).toHaveAttribute("aria-invalid", "true");
    expect(within(dialog).getByRole("alert")).toHaveTextContent("Regra de negócio violada.");
    // completed_at is never sent: the API sets it.
    expect(jsonBody(requests.find((r) => r.method === "POST"))).toEqual({
      title: "Comprar lâmpadas",
      description: null,
      priority: "medium",
      status: "todo",
      due_date: null,
    });
  });

  it("reads the filters from the URL and sends them to the API", async () => {
    setToken("token");
    const requests = mockApi({
      "GET /api/auth/me": () => jsonResponse(demoUser),
      "GET /api/tasks": () => jsonResponse(pageOf([task])),
    });
    renderWithProviders(<TasksPage />, "/tarefas?status=todo&status=doing&overdue=true&q=iptu&sort=-priority");
    const user = userEvent.setup();

    expect(await screen.findByText("Pagar IPTU")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "A fazer", pressed: true })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Atrasadas", pressed: true })).toBeInTheDocument();
    expect(screen.getByLabelText("Buscar")).toHaveValue("iptu");
    const lists = () => requests.filter((r) => r.url.startsWith("/api/tasks?"));
    expect(lists()[0]?.url).toBe(
      "/api/tasks?status=todo&status=doing&overdue=true&q=iptu&sort=-priority&limit=20&offset=0",
    );

    await user.click(screen.getByRole("button", { name: "Alta" }));
    await screen.findByRole("button", { name: "Alta", pressed: true });
    expect(lists().at(-1)?.url).toContain("priority=high");
  });
});
