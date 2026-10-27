import type { ValidationIssue } from "./types";

export type ApiErrorDetail = string | ValidationIssue[];

/** Non-2xx API response. `detail` is a message, or a list of issues on 422 (validation and business rules). */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: ApiErrorDetail;

  constructor(status: number, detail: ApiErrorDetail) {
    super(typeof detail === "string" ? detail : detail.map((issue) => issue.msg).join(" "));
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/** The request never got an HTTP response (server down, network off). */
export class NetworkError extends Error {
  constructor() {
    super("Não foi possível falar com o servidor. Verifique a conexão e tente novamente.");
    this.name = "NetworkError";
  }
}

const DEFAULT_MESSAGES: Record<number, string> = {
  403: "Você não tem permissão para esta operação.",
  404: "Registro não encontrado.",
  409: "Conflito com um registro existente.",
  413: "O arquivo é grande demais.",
  503: "Serviço temporariamente indisponível. Tente novamente.",
};

/**
 * Field errors of a 422, keyed by the last element of each issue's `loc` (the field name; list
 * indexes become strings). Business rule errors arrive with `loc: ["body"]`, so they show up under
 * the `body` key: treat it as a form-level message. Keeps the first message per field.
 */
export function getFieldErrors(error: unknown): Record<string, string> {
  if (!(error instanceof ApiError) || error.status !== 422 || typeof error.detail === "string") {
    return {};
  }
  const fields: Record<string, string> = {};
  for (const issue of error.detail) {
    const field = issue.loc.at(-1);
    if (field === undefined) continue;
    fields[String(field)] ??= issue.msg;
  }
  return fields;
}

/** Message to show the user for any error thrown by the API layer. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.message) return error.message;
    return DEFAULT_MESSAGES[error.status] ?? "Não foi possível concluir a operação.";
  }
  if (error instanceof NetworkError) return error.message;
  return "Algo deu errado. Tente novamente.";
}
