import { Component, type ErrorInfo, type ReactNode } from "react";
import { ErrorState } from "./ErrorState";

/** Default fallback: most render errors here are a chunk that failed to load (new deploy, network
 * drop), and reloading the page is what fixes them. */
export function ReloadErrorState({ title = "Não foi possível exibir esta parte" }: { title?: string }) {
  return (
    <ErrorState
      title={title}
      message="Recarregue a página para tentar de novo."
      retryLabel="Recarregar"
      onRetry={() => window.location.reload()}
    />
  );
}

export interface ErrorBoundaryProps {
  /** Shown instead of `children` after a render error, including a rejected `lazy` import. */
  fallback?: ReactNode;
  children: ReactNode;
}

interface State {
  failed: boolean;
}

/**
 * Keeps a render error (e.g. a lazy chunk that failed to load) inside one block of the screen
 * instead of unmounting the whole app. Wrap it outside the `Suspense` of a lazy component.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Kept for the developer console; the user sees the fallback.
    console.error("Render error caught by ErrorBoundary", error, info.componentStack);
  }

  render(): ReactNode {
    if (this.state.failed) return this.props.fallback ?? <ReloadErrorState />;
    return this.props.children;
  }
}
