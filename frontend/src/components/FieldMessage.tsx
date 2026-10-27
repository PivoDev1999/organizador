import { CircleAlert } from "lucide-react";

export function FieldHint({ id, children }: { id: string; children: string }) {
  return (
    <p id={id} className="text-sm text-slate-600">
      {children}
    </p>
  );
}

export function FieldError({ id, children }: { id: string; children: string }) {
  return (
    <p id={id} className="flex items-center gap-1 text-sm font-medium text-red-700">
      <CircleAlert aria-hidden="true" className="size-4 shrink-0" />
      {children}
    </p>
  );
}
