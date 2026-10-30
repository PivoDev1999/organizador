import { NavLink } from "react-router";
import { cn } from "@/lib/cn";
import { NAV_ITEMS, SYSTEM_ITEMS, type NavItem } from "./navigation";

function Items({ items }: { items: NavItem[] }) {
  return items.map(({ to, label, icon: Icon }) => (
    <li key={to}>
      <NavLink
        to={to}
        end={to === "/"}
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
  ));
}

/** Side menu for md screens and up: the modules, then the system pages in the footer. */
export function Sidebar() {
  return (
    <nav aria-label="Menu principal" className="hidden w-56 shrink-0 border-r border-slate-200 bg-white md:block">
      <div className="sticky top-16 flex h-[calc(100dvh-4rem)] flex-col justify-between p-3">
        <ul className="space-y-1">
          <Items items={NAV_ITEMS} />
        </ul>
        <ul className="space-y-1 border-t border-slate-200 pt-3 text-sm">
          <Items items={SYSTEM_ITEMS} />
        </ul>
      </div>
    </nav>
  );
}
