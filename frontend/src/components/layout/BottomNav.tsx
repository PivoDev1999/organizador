import { Ellipsis } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { NavLink, useLocation } from "react-router";
import { cn } from "@/lib/cn";
import { NAV_ITEMS, SYSTEM_ITEMS } from "./navigation";

const PRIMARY = NAV_ITEMS.filter((item) => item.primary);
const MORE = NAV_ITEMS.filter((item) => !item.primary);
const ALL_MORE = [...MORE, ...SYSTEM_ITEMS];

const itemClass = (active: boolean) =>
  cn(
    "flex min-h-14 flex-1 flex-col items-center justify-center gap-0.5 text-xs font-medium",
    active ? "text-brand-700" : "text-slate-600",
  );

/** Bottom bar for phones: main modules plus a "Mais" menu with the others. */
export function BottomNav() {
  const [open, setOpen] = useState(false);
  const { pathname } = useLocation();
  const menuId = useId();
  const containerRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const moreActive = ALL_MORE.some((item) => pathname.startsWith(item.to));

  // Close on navigation.
  const [lastPath, setLastPath] = useState(pathname);
  if (pathname !== lastPath) {
    setLastPath(pathname);
    setOpen(false);
  }

  useEffect(() => {
    if (!open) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      }
    }
    function onPointerDown(event: PointerEvent) {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("pointerdown", onPointerDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("pointerdown", onPointerDown);
    };
  }, [open]);

  return (
    <div ref={containerRef} className="fixed inset-x-0 bottom-0 z-40 md:hidden">
      {open && (
        <ul
          id={menuId}
          className="mx-2 mb-2 space-y-1 rounded-xl border border-slate-200 bg-white p-2 shadow-lg"
        >
          {ALL_MORE.map(({ to, label, icon: Icon }, index) => (
            // A line between the modules and the system pages.
            <li key={to} className={cn(index === MORE.length && "mt-1 border-t border-slate-200 pt-1")}>
              <NavLink
                to={to}
                className={({ isActive }) =>
                  cn(
                    "flex min-h-11 items-center gap-3 rounded-lg px-3 font-medium",
                    isActive ? "bg-brand-50 text-brand-800" : "text-slate-700 hover:bg-slate-100",
                  )
                }
              >
                <Icon aria-hidden="true" className="size-5" />
                {label}
              </NavLink>
            </li>
          ))}
        </ul>
      )}
      <nav
        aria-label="Menu principal"
        className="flex border-t border-slate-200 bg-white pb-[env(safe-area-inset-bottom)]"
      >
        {PRIMARY.map(({ to, label, icon: Icon }) => (
          <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => itemClass(isActive)}>
            <Icon aria-hidden="true" className="size-6" />
            {label}
          </NavLink>
        ))}
        <button
          ref={buttonRef}
          type="button"
          aria-expanded={open}
          aria-controls={menuId}
          onClick={() => setOpen((value) => !value)}
          className={itemClass(open || moreActive)}
        >
          <Ellipsis aria-hidden="true" className="size-6" />
          Mais
        </button>
      </nav>
    </div>
  );
}
