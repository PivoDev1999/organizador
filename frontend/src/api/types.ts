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
export type SystemStatus = Schemas["SystemStatusRead"];
export type CheckStatus = Schemas["CheckStatus"];
export type BackupState = Schemas["BackupState"];
export type OverallStatus = Schemas["Overall"];

export type TaskStatus = Schemas["TaskStatus"];
export type TaskPriority = Schemas["TaskPriority"];
export type TaskSort = Schemas["TaskSort"];
export type TaskCreate = Schemas["TaskCreate"];
export type TaskUpdate = Schemas["TaskUpdate"];

export type Routine = Schemas["RoutineRead"];
export type RoutineFrequency = Schemas["RoutineFrequency"];
export type RoutineCreate = Schemas["RoutineCreate"];
export type RoutineUpdate = Schemas["RoutineUpdate"];
export type RoutineLog = Schemas["RoutineLogRead"];

export type PantrySort = Schemas["PantrySort"];
export type PantryAlerts = Schemas["PantryAlertsRead"];
export type PantryItemCreate = Schemas["PantryItemCreate"];
export type PantryItemUpdate = Schemas["PantryItemUpdate"];

export type ShoppingItem = Schemas["ShoppingItemRead"];
export type ShoppingPurchase = Schemas["ShoppingPurchaseRead"];
export type ShoppingSummary = Schemas["ShoppingSummaryRead"];
export type ShoppingItemCreate = Schemas["ShoppingItemCreate"];
export type ShoppingItemUpdate = Schemas["ShoppingItemUpdate"];

export type Pet = Schemas["PetRead"];
export type PetSort = Schemas["PetSort"];
export type PetCreate = Schemas["PetCreate"];
export type PetUpdate = Schemas["PetUpdate"];
export type PetEvent = Schemas["PetEventRead"];
export type PetEventCreate = Schemas["PetEventCreate"];
export type PetEventUpdate = Schemas["PetEventUpdate"];

export type TransactionType = Schemas["TransactionType"];
export type TransactionStatus = Schemas["TransactionStatus"];
export type TransactionSort = Schemas["TransactionSort"];
export type TransactionCreate = Schemas["TransactionCreate"];
export type TransactionUpdate = Schemas["TransactionUpdate"];
export type BudgetCreate = Schemas["BudgetCreate"];
export type BudgetUpdate = Schemas["BudgetUpdate"];
export type BudgetCopy = Schemas["BudgetCopyRead"];

/** Same shape as every `Page_*Read_` of the API: one page plus the total of matches. */
export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

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
