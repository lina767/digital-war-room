import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  sectionLabel?: string;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

/**
 * Catches React errors in the tree and shows a fallback instead of crashing.
 * Use around panel sections so one failing section does not break the whole panel.
 */
export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("[ErrorBoundary]", this.props.sectionLabel ?? "Section", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <div className="rounded border border-destructive/50 bg-destructive/5 px-3 py-2 text-[11px] text-muted-foreground">
          {this.props.sectionLabel ? (
            <>This section ({this.props.sectionLabel}) could not be loaded.</>
          ) : (
            <>This section could not be loaded.</>
          )}
        </div>
      );
    }
    return this.props.children;
  }
}
