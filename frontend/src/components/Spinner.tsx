import { LoaderCircle } from "lucide-react";
import { cn } from "@/lib/cn";

export function Spinner({ label = "Carregando...", className }: { label?: string; className?: string }) {
  return (
    <span role="status" className={cn("inline-flex items-center gap-2 text-slate-600", className)}>
      <LoaderCircle aria-hidden="true" className="size-5 animate-spin" />
      <span className="sr-only">{label}</span>
    </span>
  );
}

export function FullPageSpinner({ label }: { label?: string }) {
  return (
    <div className="flex min-h-dvh items-center justify-center">
      <Spinner label={label} className="[&>svg]:size-8" />
    </div>
  );
}

/** Placeholder block while content loads. Purely visual: pair it with an accessible status. */
export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden="true" className={cn("animate-pulse rounded-md bg-slate-200", className)} />;
}

/** A few skeleton rows with a screen reader announcement. */
export function SkeletonList({ rows = 3, label = "Carregando..." }: { rows?: number; label?: string }) {
  return (
    <div role="status" className="space-y-2">
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }, (_, index) => (
        <Skeleton key={index} className="h-12 w-full" />
      ))}
    </div>
  );
}
