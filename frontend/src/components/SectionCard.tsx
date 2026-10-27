import { ChevronRight, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router";
import { cn } from "@/lib/cn";
import { Card } from "./Card";

export interface SectionCardProps {
  title: string;
  icon?: LucideIcon;
  /** Page with the full list; shows a "Ver todas" link in the header. */
  to?: string;
  linkLabel?: string;
  className?: string;
  children: ReactNode;
}

/** Card of a summary screen: titled section with an optional link to the module's page. */
export function SectionCard({ title, icon, to, linkLabel = "Ver todas", className, children }: SectionCardProps) {
  return (
    <Card
      title={title}
      icon={icon}
      className={cn("flex flex-col", className)}
      actions={
        to && (
          <Link
            to={to}
            className="inline-flex min-h-9 items-center gap-0.5 rounded-md px-1 text-sm font-medium text-brand-800 hover:underline"
          >
            {linkLabel}
            <span className="sr-only">: {title}</span>
            <ChevronRight aria-hidden="true" className="size-4" />
          </Link>
        )
      }
    >
      {children}
    </Card>
  );
}
