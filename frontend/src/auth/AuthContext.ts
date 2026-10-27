import { createContext } from "react";
import type { User } from "@/api/types";

export type AuthStatus = "anonymous" | "loading" | "authenticated" | "error";

export interface AuthContextValue {
  status: AuthStatus;
  user: User | null;
  /** Error loading the user (only when status is "error"). */
  error: unknown;
  retry: () => void;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);
