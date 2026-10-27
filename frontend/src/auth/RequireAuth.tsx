import { Navigate, Outlet, useLocation } from "react-router";
import { errorMessage } from "@/api/errors";
import { ErrorState } from "@/components/ErrorState";
import { FullPageSpinner } from "@/components/Spinner";
import { loginPath } from "./redirect";
import { useAuth } from "./useAuth";

/** Guards the app routes: anonymous users go to /login, keeping the page they asked for. */
export function RequireAuth() {
  const { status, error, retry } = useAuth();
  const location = useLocation();

  if (status === "anonymous") {
    return <Navigate to={loginPath(location.pathname + location.search + location.hash)} replace />;
  }
  if (status === "loading") return <FullPageSpinner label="Carregando sua conta..." />;
  if (status === "error") {
    return (
      <main className="mx-auto max-w-md p-6">
        <ErrorState title="Não foi possível carregar sua conta" message={errorMessage(error)} onRetry={retry} />
      </main>
    );
  }
  return <Outlet />;
}
