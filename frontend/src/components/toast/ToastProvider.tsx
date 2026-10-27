import { CircleCheck, Info, TriangleAlert, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { cn } from "@/lib/cn";
import { ToastContext, type ToastApi, type ToastVariant } from "./ToastContext";

interface Toast {
  id: number;
  message: string;
  variant: ToastVariant;
}

const DURATION_MS = 6000;
const MAX_VISIBLE = 4;

const STYLES: Record<ToastVariant, { box: string; icon: typeof Info }> = {
  success: { box: "border-emerald-700 bg-emerald-50 text-emerald-900", icon: CircleCheck },
  error: { box: "border-red-700 bg-red-50 text-red-900", icon: TriangleAlert },
  info: { box: "border-slate-400 bg-white text-slate-900", icon: Info },
};

/** Small notifications (no extra library). Errors use an assertive live region, the rest polite. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>());

  const dismiss = useCallback((id: number) => {
    clearTimeout(timers.current.get(id));
    timers.current.delete(id);
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const show = useCallback(
    (variant: ToastVariant, message: string) => {
      const id = nextId.current++;
      setToasts((current) => [...current, { id, message, variant }].slice(-MAX_VISIBLE));
      timers.current.set(
        id,
        setTimeout(() => dismiss(id), DURATION_MS),
      );
    },
    [dismiss],
  );

  useEffect(() => {
    const pending = timers.current;
    return () => pending.forEach((timer) => clearTimeout(timer));
  }, []);

  const api = useMemo<ToastApi>(
    () => ({
      success: (message) => show("success", message),
      error: (message) => show("error", message),
      info: (message) => show("info", message),
    }),
    [show],
  );

  const renderList = (assertive: boolean) => (
    <div
      aria-live={assertive ? "assertive" : "polite"}
      className="flex flex-col gap-2"
    >
      {toasts
        .filter((toast) => (toast.variant === "error") === assertive)
        .map((toast) => {
          const { box, icon: Icon } = STYLES[toast.variant];
          return (
            <div
              key={toast.id}
              className={cn("pointer-events-auto flex items-start gap-2 rounded-lg border-l-4 p-3 shadow-lg", box)}
            >
              <Icon aria-hidden="true" className="mt-0.5 size-5 shrink-0" />
              <p className="flex-1 text-sm">{toast.message}</p>
              <button
                type="button"
                onClick={() => dismiss(toast.id)}
                className="rounded p-1 hover:bg-black/5"
                aria-label="Fechar aviso"
              >
                <X aria-hidden="true" className="size-4" />
              </button>
            </div>
          );
        })}
    </div>
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      {/* Above the mobile bottom bar; bottom-right on larger screens. */}
      <div className="pointer-events-none fixed inset-x-0 bottom-20 z-[60] flex flex-col gap-2 px-4 md:inset-x-auto md:right-4 md:bottom-4 md:w-96 md:px-0">
        {renderList(true)}
        {renderList(false)}
      </div>
    </ToastContext.Provider>
  );
}
