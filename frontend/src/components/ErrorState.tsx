import { RefreshCw, TriangleAlert } from "lucide-react";
import { Button } from "./Button";

export interface ErrorStateProps {
  title?: string;
  message: string;
  onRetry?: () => void;
}

export function ErrorState({ title = "Algo deu errado", message, onRetry }: ErrorStateProps) {
  return (
    <div role="alert" className="flex flex-col items-center gap-2 px-4 py-8 text-center">
      <TriangleAlert aria-hidden="true" className="size-10 text-red-700" />
      <p className="font-medium text-slate-900">{title}</p>
      <p className="max-w-sm text-sm text-slate-700">{message}</p>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry} className="mt-2">
          <RefreshCw aria-hidden="true" className="size-4" />
          Tentar novamente
        </Button>
      )}
    </div>
  );
}
