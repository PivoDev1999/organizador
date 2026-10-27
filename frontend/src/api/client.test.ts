import { describe, expect, it } from "vitest";
import { getToken, setToken } from "@/auth/token";
import { jsonResponse, mockApi } from "@/test/utils";
import { apiFetch } from "./client";
import { ApiError, getFieldErrors } from "./errors";

describe("apiFetch", () => {
  it("turns a 422 into an ApiError with errors per field (last element of loc)", async () => {
    mockApi({
      "GET /api/auth/me": () =>
        jsonResponse(
          {
            detail: [
              { type: "missing", loc: ["body", "title"], msg: "Campo obrigatório." },
              { type: "greater_than", loc: ["body", "items", 0, "amount"], msg: "O valor deve ser maior que 0." },
              { type: "string_type", loc: ["body", "title"], msg: "Informe um texto." },
              { type: "value_error", loc: ["body"], msg: "A data final deve ser posterior à inicial." },
            ],
          },
          422,
        ),
    });

    const error = await apiFetch("/api/auth/me").catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(422);
    expect(getFieldErrors(error)).toEqual({
      title: "Campo obrigatório.",
      amount: "O valor deve ser maior que 0.",
      body: "A data final deve ser posterior à inicial.",
    });
    expect(getFieldErrors(new ApiError(409, "Conflito."))).toEqual({});
  });

  it("ignores an error body that is not the API's detail shape", async () => {
    mockApi({ "GET /api/auth/me": () => jsonResponse({ detail: [{ unexpected: true }] }, 422) });

    const error = await apiFetch("/api/auth/me").catch((caught: unknown) => caught);

    expect((error as ApiError).detail).toBe("");
    expect(getFieldErrors(error)).toEqual({});
  });

  it("keeps a newer session when a 401 of an older token arrives late", async () => {
    setToken("old-token");
    mockApi({
      "GET /api/auth/me": () => {
        setToken("new-token"); // signed in again while the old request was in flight
        return jsonResponse({ detail: "Não autenticado." }, 401);
      },
    });

    await apiFetch("/api/auth/me").catch(() => undefined);

    expect(getToken()).toBe("new-token");
  });
});
