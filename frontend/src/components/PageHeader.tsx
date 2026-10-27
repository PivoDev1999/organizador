import type { ReactNode } from "react";
import { useDocumentTitle } from "@/lib/useDocumentTitle";

export interface PageHeaderProps {
  title: string;
  /** Line under the title (e.g. a greeting with today's date). */
  description?: ReactNode;
  actions?: ReactNode;
}

export function PageHeader({ title, description, actions }: PageHeaderProps) {
  useDocumentTitle(title);
  return (
    <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
      <div className="min-w-0">
        {/* tabIndex -1: the layout moves focus here after navigation, for screen reader users. */}
        <h1 tabIndex={-1} className="text-2xl font-bold text-slate-900 focus:outline-none">
          {title}
        </h1>
        {description && <p className="mt-1 text-slate-700">{description}</p>}
      </div>
      {actions}
    </div>
  );
}
