import { apiFetch } from "./client";
import type { Token, User } from "./types";

/** OAuth2 password form: `username` carries the e-mail. */
export function login(email: string, password: string): Promise<Token> {
  return apiFetch("/api/auth/login", {
    method: "post",
    body: new URLSearchParams({ username: email, password }),
    auth: false,
  });
}

export function getMe(): Promise<User> {
  return apiFetch("/api/auth/me");
}
