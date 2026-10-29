import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { App } from "@/App";
import { demoUser, jsonResponse, mockApi, renderWithProviders } from "@/test/utils";
import { getToken, setToken } from "./token";

async function submitLogin(email: string, password: string) {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText(/E-mail/), email);
  await user.type(screen.getByLabelText(/Senha/), password);
  await user.click(screen.getByRole("button", { name: "Entrar" }));
}

describe("authentication", () => {
  it("logs in with a form-encoded request and opens the requested page", async () => {
    const requests = mockApi({
      "POST /api/auth/login": () => jsonResponse({ access_token: "token-123", token_type: "bearer" }),
      "GET /api/auth/me": ({ headers }) =>
        headers.get("Authorization") === "Bearer token-123"
          ? jsonResponse(demoUser)
          : jsonResponse({ detail: "Não autenticado." }, 401),
    });
    renderWithProviders(<App />, "/login?next=%2Ftarefas");

    await submitLogin("demo@organizador.local", "s3nha-forte");

    expect(await screen.findByRole("heading", { level: 1, name: "Tarefas" })).toBeInTheDocument();
    expect(screen.getByText("Demo")).toBeInTheDocument();
    expect(getToken()).toBe("token-123");
    const body = requests.find((r) => r.method === "POST")?.body;
    expect(body).toBeInstanceOf(URLSearchParams);
    expect(Object.fromEntries(body as URLSearchParams)).toEqual({
      username: "demo@organizador.local",
      password: "s3nha-forte",
    });
  });

  it("shows a generic message when the credentials are wrong", async () => {
    mockApi({ "POST /api/auth/login": () => jsonResponse({ detail: "E-mail ou senha incorretos." }, 401) });
    renderWithProviders(<App />, "/login");

    await submitLogin("demo@organizador.local", "errada");

    expect(await screen.findByRole("alert")).toHaveTextContent("E-mail ou senha inválidos.");
    expect(screen.getByLabelText(/Senha/)).toHaveFocus();
    expect(screen.getByLabelText(/Senha/)).toHaveValue("");
    expect(getToken()).toBeNull();
  });

  it("asks to wait when the proxy rate-limits the login (429)", async () => {
    // Nginx answers the limit with its own HTML page, not the API's JSON.
    mockApi({
      "POST /api/auth/login": () =>
        new Response("<html>429 Too Many Requests</html>", { status: 429, headers: { "Content-Type": "text/html" } }),
    });
    renderWithProviders(<App />, "/login");

    await submitLogin("demo@organizador.local", "errada");

    expect(await screen.findByRole("alert")).toHaveTextContent("Muitas tentativas. Aguarde um minuto e tente de novo.");
    expect(getToken()).toBeNull();
  });

  it("on a 401 clears the token, goes to /login and returns to the original page after login", async () => {
    setToken("expired");
    mockApi({
      "GET /api/auth/me": ({ headers }) =>
        headers.get("Authorization") === "Bearer fresh"
          ? jsonResponse(demoUser)
          : jsonResponse({ detail: "Não autenticado." }, 401),
      "POST /api/auth/login": () => jsonResponse({ access_token: "fresh", token_type: "bearer" }),
    });
    renderWithProviders(<App />, "/mercado?filtro=pendentes");

    expect(await screen.findByRole("button", { name: "Entrar" })).toBeInTheDocument();
    expect(getToken()).toBeNull();

    await submitLogin("demo@organizador.local", "s3nha-forte");

    expect(await screen.findByRole("heading", { level: 1, name: "Mercado" })).toBeInTheDocument();
  });
});
