import { CircleAlert } from "lucide-react";

/** Error of the whole form (business rules sent with `loc: ["body"]`, network). Nothing when null. */
export function FormError({ message }: { message: string | null | undefined }) {
  if (!message) return null;
  return (
    <p role="alert" className="flex items-start gap-2 rounded-lg bg-red-50 p-3 text-sm font-medium text-red-800">
      <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
      {message}
    </p>
  );
}
