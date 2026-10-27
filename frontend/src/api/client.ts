import { clearToken, getToken } from "@/auth/token";
import { ApiError, NetworkError, type ApiErrorDetail } from "./errors";
import type {
  ApiPath,
  ApiResponse,
  HttpMethod,
  JsonBody,
  PathParams,
  PathsWith,
  QueryParams,
} from "./types";

export interface RequestOptions<P extends ApiPath, M extends HttpMethod> {
  method?: M;
  /** Values for the `{placeholders}` of the path. */
  params?: PathParams<P, M>;
  query?: QueryParams<P, M>;
  /** JSON body (serialized here). For forms and uploads use `body` instead. */
  json?: JsonBody<P, M>;
  body?: FormData | URLSearchParams;
  /** false: no Authorization header and no session handling on 401 (login). Default true. */
  auth?: boolean;
  signal?: AbortSignal;
}

function buildUrl(path: string, params: object | undefined, query: object | undefined): string {
  let url = path.replace(/\{(\w+)\}/g, (_, name: string) => {
    const value: unknown = params ? (params as Record<string, unknown>)[name] : undefined;
    if (value === undefined || value === null) throw new Error(`Missing path parameter: ${name}`);
    return encodeURIComponent(String(value));
  });
  if (query) {
    const search = new URLSearchParams();
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null) continue;
      for (const item of Array.isArray(value) ? value : [value]) search.append(key, String(item));
    }
    const qs = search.toString();
    if (qs) url += `?${qs}`;
  }
  return url;
}

function isIssue(value: unknown): boolean {
  if (!value || typeof value !== "object") return false;
  const issue = value as { loc?: unknown; msg?: unknown };
  return Array.isArray(issue.loc) && typeof issue.msg === "string";
}

/** The API sends a string or a list of {type, loc, msg}; anything else (e.g. a proxy page) is ignored. */
function isDetail(value: unknown): value is ApiErrorDetail {
  return typeof value === "string" || (Array.isArray(value) && value.every(isIssue));
}

async function readErrorDetail(response: Response): Promise<ApiErrorDetail> {
  try {
    const body: unknown = await response.json();
    if (body && typeof body === "object" && "detail" in body && isDetail(body.detail)) {
      return body.detail;
    }
  } catch {
    // Not JSON (e.g. an HTML error page from a proxy).
  }
  return "";
}

/** Sends the request with the session token and turns non-2xx responses into ApiError. */
async function send<P extends ApiPath, M extends HttpMethod>(
  path: P,
  options: RequestOptions<P, M>,
  accept: string,
): Promise<Response> {
  const { method = "get", params, query, json, body, auth = true, signal } = options;
  const headers = new Headers({ Accept: accept });
  const token = auth ? getToken() : null;
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let payload: BodyInit | undefined = body;
  if (json !== undefined) {
    headers.set("Content-Type", "application/json");
    payload = JSON.stringify(json);
  }

  let response: Response;
  try {
    response = await fetch(buildUrl(path, params ?? undefined, query ?? undefined), {
      method: method.toUpperCase(),
      headers,
      body: payload,
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new NetworkError();
  }

  if (!response.ok) {
    // Expired or invalid session: dropping the token makes the protected routes send the user to
    // /login, keeping the current page to come back after signing in (see RequireAuth). A late 401 of
    // a request sent with an older token must not log out the session that replaced it.
    if (response.status === 401 && token !== null && getToken() === token) clearToken();
    throw new ApiError(response.status, await readErrorDetail(response));
  }
  return response;
}

/** JSON request typed by the OpenAPI schema: path, params, query, body and response. */
export async function apiFetch<P extends PathsWith<M>, M extends HttpMethod = "get">(
  path: P,
  options: RequestOptions<P, M> = {},
): Promise<ApiResponse<P, M>> {
  const response = await send(path, options, "application/json");
  if (response.status === 204) return undefined as ApiResponse<P, M>;
  return (await response.json()) as ApiResponse<P, M>;
}

/** Binary request (downloads). Same auth and error handling as apiFetch. */
export async function apiFetchBlob<P extends PathsWith<"get">>(
  path: P,
  options: RequestOptions<P, "get"> = {},
): Promise<Blob> {
  const response = await send(path, options, "*/*");
  return response.blob();
}
