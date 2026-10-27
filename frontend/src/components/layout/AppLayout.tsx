import { LogOut } from "lucide-react";
import { useEffect, useRef } from "react";
import { Outlet, useLocation } from "react-router";
import { useAuth } from "@/auth/useAuth";
import { Button } from "@/components/Button";
import { BottomNav } from "./BottomNav";
import { Sidebar } from "./Sidebar";

export function AppLayout() {
  const { user, logout } = useAuth();
  const { pathname } = useLocation();
  const mainRef = useRef<HTMLElement>(null);
  const firstRender = useRef(true);

  // After client-side navigation, move focus to the new page title so screen readers announce it.
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    mainRef.current?.querySelector<HTMLElement>("h1")?.focus();
  }, [pathname]);

  return (
    <div className="flex min-h-dvh flex-col">
      <a
        href="#conteudo"
        className="sr-only z-50 rounded bg-white px-3 py-2 focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
      >
        Pular para o conteúdo
      </a>
      <header className="sticky top-0 z-30 flex h-16 items-center justify-between gap-3 border-b border-slate-200 bg-white px-4">
        <span className="text-lg font-bold text-brand-800">Organizador</span>
        <div className="flex min-w-0 items-center gap-2">
          <span className="truncate text-sm text-slate-700" title={user?.email}>
            {user?.name}
          </span>
          <Button variant="ghost" size="sm" onClick={logout}>
            <LogOut aria-hidden="true" className="size-4" />
            Sair
          </Button>
        </div>
      </header>
      <div className="flex flex-1">
        <Sidebar />
        <main ref={mainRef} id="conteudo" tabIndex={-1} className="min-w-0 flex-1 p-4 pb-28 md:p-8 md:pb-8">
          <div className="mx-auto max-w-5xl">
            <Outlet />
          </div>
        </main>
      </div>
      <BottomNav />
    </div>
  );
}
