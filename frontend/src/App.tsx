import { Route, Routes } from "react-router";
import { RequireAuth } from "@/auth/RequireAuth";
import { AppLayout } from "@/components/layout/AppLayout";
import { DashboardPage } from "@/pages/DashboardPage";
import { FinancePage } from "@/pages/FinancePage";
import { LoginPage } from "@/pages/LoginPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { PantryPage } from "@/pages/PantryPage";
import { PetsPage } from "@/pages/PetsPage";
import { RoutinesPage } from "@/pages/RoutinesPage";
import { ShoppingPage } from "@/pages/ShoppingPage";
import { TasksPage } from "@/pages/TasksPage";

/** Route table. Providers (router, query client, auth, toasts) are set up in AppProviders. */
export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route element={<AppLayout />}>
          <Route index element={<DashboardPage />} />
          <Route path="tarefas" element={<TasksPage />} />
          <Route path="rotina" element={<RoutinesPage />} />
          <Route path="despensa" element={<PantryPage />} />
          <Route path="mercado" element={<ShoppingPage />} />
          <Route path="pets" element={<PetsPage />} />
          <Route path="financas" element={<FinancePage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Route>
    </Routes>
  );
}
