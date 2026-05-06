import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        this.props.fallback ?? (
          <div className="rounded-xl bg-surface-card border border-accent-red/30 p-5 text-sm text-accent-red">
            <p className="font-semibold mb-1">Something went wrong</p>
            <p className="text-xs text-gray-400 font-mono whitespace-pre-wrap">
              {this.state.error.message}
            </p>
          </div>
        )
      );
    }
    return this.props.children;
  }
}
