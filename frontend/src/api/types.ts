// Aliases over the generated OpenAPI types (schema.d.ts) plus helpers that derive request and
// response types from `paths`, so the client follows the API contract without hand-written copies.
import type { components, paths } from "./schema";

export type Schemas = components["schemas"];
export type User = Schemas["UserRead"];
export type Token = Schemas["Token"];
export type FileRead = Schemas["FileRead"];
export type FileEntityType = Schemas["FileEntityType"];
export type ValidationIssue = Schemas["ValidationError"];
export type Dashboard = Schemas["DashboardRead"];
export type Task = Schemas["TaskRead"];
export type RoutineToday = Schemas["RoutineTodayRead"];
export type PantryItem = Schemas["PantryItemRead"];
export type PetReminder = Schemas["PetReminderRead"];
export type PetEventType = Schemas["PetEventType"];
export type Transaction = Schemas["TransactionRead"];
export type MonthTotals = Schemas["MonthTotalsRead"];
export type MonthSummary = Schemas["SummaryRead"];
export type CategoryTotals = Schemas["CategoryTotalsRead"];
export type Budget = Schemas["BudgetRead"];
export type BudgetAlert = Schemas["BudgetAlertRead"];
export type BudgetAlertLevel = Schemas["BudgetAlertLevel"];

export type HttpMethod = "get" | "post" | "put" | "patch" | "delete";

export type ApiPath = keyof paths;

/** Paths that implement method M (methods missing from a path are typed `?: never`). */
export type PathsWith<M extends HttpMethod> = {
  [P in ApiPath]: paths[P] extends Record<M, object> ? P : never;
}[ApiPath];

export type Operation<P extends ApiPath, M extends HttpMethod> = NonNullable<paths[P][M]>;

type Responses<O> = O extends { responses: infer R } ? R : never;
type SuccessResponse<R> = 200 extends keyof R ? R[200] : 201 extends keyof R ? R[201] : never;
type JsonContent<R> = R extends { content: { "application/json": infer B } } ? B : undefined;

/** Body of the success response (200/201) of an operation; `undefined` for 204. */
export type ApiResponse<P extends ApiPath, M extends HttpMethod> =
  204 extends keyof Responses<Operation<P, M>>
    ? undefined
    : JsonContent<SuccessResponse<Responses<Operation<P, M>>>>;

export type PathParams<P extends ApiPath, M extends HttpMethod> =
  Operation<P, M> extends { parameters: { path: infer T } } ? T : never;

export type QueryParams<P extends ApiPath, M extends HttpMethod> =
  Operation<P, M> extends { parameters: { query?: infer T } } ? T : never;

export type JsonBody<P extends ApiPath, M extends HttpMethod> =
  Operation<P, M> extends { requestBody?: { content: { "application/json": infer B } } } ? B : never;
