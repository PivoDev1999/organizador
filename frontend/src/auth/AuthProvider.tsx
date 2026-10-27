import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useSyncExternalStore, type ReactNode } from "react";
import { useNavigate } from "react-router";
import { getMe, login as loginRequest } from "@/api/auth";
import { AuthContext, type AuthContextValue, type AuthStatus } from "./AuthContext";
import { clearToken, getToken, setToken, subscribeToken } from "./token";

export const ME_QUERY_KEY = ["auth", "me"] as const;

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const token = useSyncExternalStore(subscribeToken, getToken, () => null);

  const me = useQuery({
    queryKey: ME_QUERY_KEY,
    queryFn: getMe,
    enabled: token !== null,
    staleTime: Infinity,
  });

  // Session ended or replaced (logout, 401, another account in another tab): drop every cached
  // response of the previous user. Not on the first login, so anonymous screens keep their queries.
  const previousToken = useRef(token);
  useEffect(() => {
    if (previousToken.current !== null && previousToken.current !== token) queryClient.clear();
    previousToken.current = token;
  }, [token, queryClient]);

  const login = useCallback(
    async (email: string, password: string) => {
      const { access_token } = await loginRequest(email, password);
      setToken(access_token);
      try {
        await queryClient.fetchQuery({ queryKey: ME_QUERY_KEY, queryFn: getMe });
      } catch (error) {
        clearToken(); // Do not keep a session whose user could not be loaded.
        throw error;
      }
    },
    [queryClient],
  );

  const logout = useCallback(() => {
    navigate("/login", { replace: true });
    clearToken();
  }, [navigate]);

  const { refetch } = me;
  const retry = useCallback(() => void refetch(), [refetch]);

  let status: AuthStatus;
  if (token === null) status = "anonymous";
  else if (me.data) status = "authenticated";
  else if (me.isError) status = "error";
  else status = "loading";

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user: token !== null ? (me.data ?? null) : null,
      error: me.error,
      retry,
      login,
      logout,
    }),
    [status, token, me.data, me.error, retry, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
