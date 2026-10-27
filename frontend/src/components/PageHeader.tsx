import type { ReactNode } from "react";
import { useDocumentTitle } from "@/lib/useDocumentTitle";

export function PageHeader({ title, actions }: { title: string; actions?: ReactNode }) {
  useDocumentTitle(title);
  return (
    <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
      {/* tabIndex -1: the layout moves focus here after navigation, for screen reader users. */}
      <h1 tabIndex={-1} className="text-2xl font-bold text-slate-900 focus:outline-none">
        {title}
      </h1>
      {actions}
    </div>
  );
}
