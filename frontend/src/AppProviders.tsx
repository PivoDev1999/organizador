import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { AuthProvider } from "@/auth/AuthProvider";
import { ToastProvider } from "@/components/toast/ToastProvider";

/** Providers that need a router above them (AuthProvider navigates on logout). */
export function AppProviders({ client, children }: { client: QueryClient; children: ReactNode }) {
  return (
    <QueryClientProvider client={client}>
      <ToastProvider>
        <AuthProvider>{children}</AuthProvider>
      </ToastProvider>
    </QueryClientProvider>
  );
}
