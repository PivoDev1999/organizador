import { createContext } from "react";

export type ToastVariant = "success" | "error" | "info";

export interface ToastApi {
  success: (message: string) => void;
  error: (message: string) => void;
  info: (message: string) => void;
}

export const ToastContext = createContext<ToastApi | null>(null);
