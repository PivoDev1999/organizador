import type { LucideIcon } from "lucide-react";
import { LayoutDashboard, ListChecks, Package, PawPrint, Repeat, ShoppingCart, Wallet } from "lucide-react";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  /** Shown in the mobile bottom bar; the others go under "Mais". */
  primary: boolean;
}

export const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Painel", icon: LayoutDashboard, primary: true },
  { to: "/tarefas", label: "Tarefas", icon: ListChecks, primary: true },
  { to: "/rotina", label: "Rotina", icon: Repeat, primary: false },
  { to: "/mercado", label: "Mercado", icon: ShoppingCart, primary: true },
  { to: "/despensa", label: "Despensa", icon: Package, primary: false },
  { to: "/pets", label: "Pets", icon: PawPrint, primary: false },
  { to: "/financas", label: "Finanças", icon: Wallet, primary: true },
];
