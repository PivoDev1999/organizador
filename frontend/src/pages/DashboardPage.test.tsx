import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Budget, Dashboard, MonthSummary, RoutineToday, Task } from "@/api/types";
import { setToken } from "@/auth/token";
import { demoUser, jsonResponse, mockApi, renderWithProviders } from "@/test/utils";
import { DashboardPage } from "./DashboardPage";

// Testing Library normalizes whitespace in text queries: the no-break space of formatMoney matches " ".
const STAMP = "2026-10-20T12:00:00Z";

const task = (id: string, title: string, dueDate: string): Task => ({
  id,
  title,
  description: null,
  status: "todo",
  priority: "medium",
  due_date: dueDate,
  completed_at: null,
  created_at: STAMP,
  updated_at: STAMP,
});

const routine = (id: string, name: string, doneToday: boolean): RoutineToday => ({
  id,
  name,
  description: null,
  frequency: "daily",
  days_of_week: null,
  day_of_month: null,
  time_of_day: null,
  is_active: true,
  created_at: STAMP,
  updated_at: STAMP,
  done_today: doneToday,
});

const totals = (total: string, paid: string, pending: string) => ({ total, paid, pending });

function makeDashboard(routines: RoutineToday[]): Dashboard {
  return {
    date: "2026-10-27",
    tasks: {
      overdue: { items: [task("t1", "Pagar IPTU", "2026-10-20"), task("t2", "Trocar filtro", "2026-10-25")], total: 5 },
      due_today: { items: [task("t3", "Ligar para o encanador", "2026-10-27")], total: 1 },
      doing_total: 2,
    },
    routines: { due_today: routines, done: routines.filter((r) => r.done_today).length, total: routines.length },
    pantry: { low_stock: { items: [], total: 0 }, expired: { items: [], total: 0 }, expiring_soon: { items: [], total: 0 } },
    shopping: { pending: 4, estimated_total: "87.30" },
    pets: {
      reminders: {
        items: [
          {
            event_id: "e1",
            pet_id: "p1",
            pet_name: "Rex",
            type: "vaccine",
            description: "V10",
            occurred_on: "2025-10-20",
            next_due_on: "2026-10-20",
            overdue: true,
          },
        ],
        total: 1,
      },
    },
    finance: {
      upcoming: { items: [], total: 0 },
      month: {
        month: "2026-10",
        income: totals("5000.00", "5000.00", "0.00"),
        expense: totals("5200.00", "4000.00", "1200.00"),
        balance: { total: "-200.00", paid: "1000.00" },
      },
      budget_alerts: { items: [], total: 0 },
    },
  };
}

const summary: MonthSummary = {
  month: "2026-10",
  income: totals("5000.00", "5000.00", "0.00"),
  expense: totals("5200.00", "4000.00", "1200.00"),
  balance: { total: "-200.00", paid: "1000.00" },
  by_category: [{ type: "expense", category: "Mercado", ...totals("5200.00", "4000.00", "1200.00") }],
};

const budgets: Budget[] = [
  { id: "b1", category: "Mercado", month: "2026-10", amount: "5000.00", spent: "5200.00", remaining: "-200.00", percent_used: "104.0" },
];

/** Logged-in demo user and a fake API where routine logs change the stored dashboard. */
function setup(routines: RoutineToday[], logStatus: (id: string) => number = () => 201) {
  setToken("token");
  let dashboard = makeDashboard(routines);
  const requests = mockApi({
    "GET /api/auth/me": () => jsonResponse(demoUser),
    "GET /api/dashboard": () => jsonResponse(dashboard),
    "GET /api/transactions/summary": () => jsonResponse(summary),
    "GET /api/budgets": () => jsonResponse(budgets),
    ...Object.fromEntries(
      routines.map((r) => [
        `POST /api/routines/${r.id}/logs`,
        () => {
          const status = logStatus(r.id);
          if (status === 201 || status === 409) {
            dashboard = makeDashboard(dashboard.routines.due_today.map((x) => (x.id === r.id ? { ...x, done_today: true } : x)));
          }
          return status === 201
            ? jsonResponse({ id: "log", routine_id: r.id, done_on: "2026-10-27", note: null, created_at: STAMP }, 201)
            : jsonResponse({ detail: status === 409 ? "Rotina já marcada hoje." : "Erro interno." }, status);
        },
      ]),
    ),
  });
  renderWithProviders(<DashboardPage />);
  return requests;
}

const section = (name: string) => screen.getByRole("region", { name });

describe("DashboardPage", () => {
  it("renders every section from the API data", async () => {
    const requests = setup([routine("r1", "Regar plantas", true)]);

    const today = await screen.findByText("terça-feira, 27 de outubro");
    expect(today.parentElement).toHaveTextContent("Olá, Demo! Hoje é terça-feira, 27 de outubro.");
    expect(requests.find((r) => r.url.startsWith("/api/dashboard"))?.url).toBe("/api/dashboard?within=7&limit=5");

    expect(within(section("Afazeres")).getByText("Pagar IPTU")).toBeInTheDocument();
    expect(within(section("Afazeres")).getByText("em andamento").parentElement).toHaveTextContent("2");
    expect(within(section("Afazeres")).getByRole("link", { name: /Ver todas/ })).toHaveAttribute("href", "/tarefas");
    expect(within(section("Rotina de hoje")).getByText("1 de 1 feitas")).toBeInTheDocument();
    expect(within(section("Mercado")).getByText("R$ 87,30")).toBeInTheDocument();
    const pets = section("Pets");
    expect(within(pets).getByText("Rex")).toBeInTheDocument();
    expect(within(pets).getByText(/Vacina/)).toBeInTheDocument();
    expect(within(pets).getByText("atrasado")).toBeInTheDocument();
    expect(within(section("Despensa")).getByText("Nada vencido, vencendo ou acabando.")).toBeInTheDocument();
    expect(within(section("Contas a pagar")).getByText(/Nenhuma conta a pagar/)).toBeInTheDocument();
    expect(within(section("Resumo do mês")).getByText("-R$ 200,00")).toHaveClass("text-red-700");

    // Charts: month from the dashboard's date, data also as a table for screen readers.
    const categories = await screen.findByRole("table", { name: "Despesas do mês por categoria" });
    expect(within(categories).getByRole("row", { name: /^Mercado R\$\s5\.200,00$/ })).toBeInTheDocument();
    const usage = await screen.findByRole("table", { name: "Uso dos orçamentos do mês" });
    expect(within(usage).getByRole("row", { name: /Mercado 104% .* estourado/ })).toBeInTheDocument();
    expect(requests.some((r) => r.url === "/api/transactions/summary?month=2026-10")).toBe(true);
    expect(requests.some((r) => r.url === "/api/budgets?month=2026-10")).toBe(true);
  });

  it("shows +N when the API has more items than it sent", async () => {
    setup([]);
    const tasks = await screen.findByRole("region", { name: "Afazeres" });
    // 5 overdue, 2 sent: "+3"; the 1 due today was sent whole, so no "+N" there.
    expect(within(tasks).getByText("+3")).toBeInTheDocument();
    expect(within(tasks).getByText("e mais 3 atrasadas")).toHaveClass("sr-only");
    expect(within(tasks).getAllByText(/^\+\d+$/)).toHaveLength(1);
  });

  it("marks routines as done and treats 409 as already done", async () => {
    const requests = setup([routine("r1", "Regar plantas", false), routine("r2", "Lavar louça", false)], (id) =>
      id === "r2" ? 409 : 201,
    );
    const user = userEvent.setup();
    const routines = await screen.findByRole("region", { name: "Rotina de hoje" });
    expect(within(routines).getByText("0 de 2 feitas")).toBeInTheDocument();

    await user.click(within(routines).getByRole("checkbox", { name: "Regar plantas" }));
    expect(await within(routines).findByText("1 de 2 feitas")).toBeInTheDocument();
    expect(within(routines).getByRole("checkbox", { name: "Regar plantas" })).toBeChecked();
    expect(within(routines).getByRole("checkbox", { name: "Regar plantas" })).toBeDisabled();

    await user.click(within(routines).getByRole("checkbox", { name: "Lavar louça" }));
    expect(await within(routines).findByText("2 de 2 feitas")).toBeInTheDocument();
    expect(screen.queryByText(/já marcada|Conflito/)).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    const posts = requests.filter((r) => r.method === "POST");
    expect(posts.map((r) => r.url)).toEqual(["/api/routines/r1/logs", "/api/routines/r2/logs"]);
    expect(posts[0]?.body).toBeUndefined(); // empty body: today
  });

  it("on a failed log rolls back only that routine, keeping others marked meanwhile", async () => {
    setToken("token");
    const dashboard = makeDashboard([routine("a", "Regar plantas", false), routine("b", "Lavar louça", false)]);
    let releaseA: (response: Response) => void = () => {};
    let loads = 0;
    mockApi({
      "GET /api/auth/me": () => jsonResponse(demoUser),
      // Only the first load answers: a refetch would hide what the cache holds after the rollback.
      "GET /api/dashboard": () => (++loads === 1 ? jsonResponse(dashboard) : new Promise<Response>(() => {})),
      "GET /api/transactions/summary": () => jsonResponse(summary),
      "GET /api/budgets": () => jsonResponse(budgets),
      "POST /api/routines/a/logs": () => new Promise<Response>((resolve) => (releaseA = resolve)),
      "POST /api/routines/b/logs": () =>
        jsonResponse({ id: "log", routine_id: "b", done_on: "2026-10-27", note: null, created_at: STAMP }, 201),
    });
    renderWithProviders(<DashboardPage />);
    const user = userEvent.setup();
    const routines = await screen.findByRole("region", { name: "Rotina de hoje" });

    await user.click(within(routines).getByRole("checkbox", { name: "Regar plantas" }));
    await user.click(within(routines).getByRole("checkbox", { name: "Lavar louça" }));
    expect(within(routines).getByText("2 de 2 feitas")).toBeInTheDocument();

    releaseA(jsonResponse({ detail: "Erro interno." }, 500));

    expect(await screen.findByText("Erro interno.")).toBeInTheDocument();
    expect(within(routines).getByText("1 de 2 feitas")).toBeInTheDocument();
    expect(within(routines).getByRole("checkbox", { name: "Regar plantas" })).not.toBeChecked();
    expect(within(routines).getByRole("checkbox", { name: "Lavar louça" })).toBeChecked();
    // The refetch only starts once the last log settled (A), not when B finished first.
    expect(loads).toBe(2);
  });

  it("shows the error state with a retry button when the dashboard fails", async () => {
    setToken("token");
    let fail = true;
    mockApi({
      "GET /api/auth/me": () => jsonResponse(demoUser),
      "GET /api/dashboard": () => (fail ? jsonResponse({ detail: "Erro interno." }, 500) : jsonResponse(makeDashboard([]))),
      "GET /api/transactions/summary": () => jsonResponse(summary),
      "GET /api/budgets": () => jsonResponse(budgets),
    });
    renderWithProviders(<DashboardPage />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Não foi possível carregar o painel");
    fail = false;
    await userEvent.setup().click(within(alert).getByRole("button", { name: "Tentar novamente" }));

    expect(await screen.findByRole("region", { name: "Afazeres" })).toBeInTheDocument();
  });
});
