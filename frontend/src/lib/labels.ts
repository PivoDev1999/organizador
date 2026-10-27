import type {
  PantrySort,
  PetEventType,
  RoutineFrequency,
  TaskPriority,
  TaskSort,
  TaskStatus,
  TransactionSort,
  TransactionStatus,
  TransactionType,
} from "@/api/types";
import type { Tone } from "@/components/tones";

export const PET_EVENT_TYPE_LABELS: Record<PetEventType, string> = {
  vaccine: "Vacina",
  vet: "Veterinário",
  medication: "Remédio",
  grooming: "Banho e tosa",
  other: "Outro",
};

export const TASK_STATUS_LABELS: Record<TaskStatus, string> = {
  todo: "A fazer",
  doing: "Em andamento",
  done: "Concluída",
};

export const TASK_PRIORITY_LABELS: Record<TaskPriority, string> = {
  low: "Baixa",
  medium: "Média",
  high: "Alta",
};

export const TASK_PRIORITY_TONES: Record<TaskPriority, Tone> = {
  low: "neutral",
  medium: "info",
  high: "warning",
};

export const TASK_SORT_LABELS: Partial<Record<TaskSort, string>> = {
  due_date: "Prazo",
  "-priority": "Prioridade",
  "-created_at": "Mais recentes",
};

export const ROUTINE_FREQUENCY_LABELS: Record<RoutineFrequency, string> = {
  daily: "Diária",
  weekly: "Semanal",
  monthly: "Mensal",
};

/** Index = API weekday (0 = domingo ... 6 = sábado). */
export const WEEKDAY_SHORT = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"] as const;
export const WEEKDAY_LONG = ["domingo", "segunda", "terça", "quarta", "quinta", "sexta", "sábado"] as const;

export const PANTRY_SORT_LABELS: Partial<Record<PantrySort, string>> = {
  name: "Nome",
  expires_on: "Validade",
};

export const TRANSACTION_TYPE_LABELS: Record<TransactionType, string> = {
  expense: "Despesa",
  income: "Receita",
};

export const TRANSACTION_STATUS_LABELS: Record<TransactionStatus, string> = {
  pending: "Pendente",
  paid: "Paga",
  overdue: "Atrasada",
};

export const TRANSACTION_SORT_LABELS: Partial<Record<TransactionSort, string>> = {
  due_date: "Vencimento",
  "-amount": "Maior valor",
  amount: "Menor valor",
};

/** Typed keys of a label map (Object.keys returns string[]). */
export function labelOptions<K extends string>(labels: Partial<Record<K, string>>): Array<{ value: K; label: string }> {
  return (Object.entries(labels) as Array<[K, string]>).map(([value, label]) => ({ value, label }));
}
