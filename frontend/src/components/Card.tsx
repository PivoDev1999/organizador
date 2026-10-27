import type { LucideIcon } from "lucide-react";
import { useId, type ComponentProps, type ReactNode } from "react";
import { cn } from "@/lib/cn";

export interface CardProps extends ComponentProps<"section"> {
  title?: string;
  /** Decorative icon before the title. */
  icon?: LucideIcon;
  actions?: ReactNode;
}

/** Surface for a block of content. With `title`, it is a section labeled by its heading. */
export function Card({ title, icon: Icon, actions, className, children, ...props }: CardProps) {
  const headingId = useId();
  return (
    <section
      aria-labelledby={title ? headingId : undefined}
      className={cn("rounded-xl border border-slate-200 bg-white p-4 shadow-sm", className)}
      {...props}
    >
      {(title || actions) && (
        <header className="mb-3 flex flex-wrap items-center justify-between gap-2">
          {title && (
            <h2 id={headingId} className="flex items-center gap-2 text-lg font-semibold text-slate-900">
              {Icon && <Icon aria-hidden="true" className="size-5 shrink-0 text-brand-700" />}
              {title}
            </h2>
          )}
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}
