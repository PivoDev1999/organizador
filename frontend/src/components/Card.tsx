import type { ComponentProps, ReactNode } from "react";
import { cn } from "@/lib/cn";

export interface CardProps extends ComponentProps<"section"> {
  title?: string;
  actions?: ReactNode;
}

/** Surface for a block of content. With `title`, it is a labeled section. */
export function Card({ title, actions, className, children, ...props }: CardProps) {
  return (
    <section className={cn("rounded-xl border border-slate-200 bg-white p-4 shadow-sm", className)} {...props}>
      {(title || actions) && (
        <header className="mb-3 flex flex-wrap items-center justify-between gap-2">
          {title && <h2 className="text-lg font-semibold text-slate-900">{title}</h2>}
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}
