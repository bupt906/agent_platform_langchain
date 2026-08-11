import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: { componentStack?: string }) {
    console.error("[ErrorBoundary]", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex h-dvh flex-col items-center justify-center gap-3 bg-slate-50 p-6 text-center">
          <p className="text-sm font-semibold text-slate-700">页面出错了</p>
          <pre className="max-w-xl overflow-auto rounded-lg bg-white px-4 py-3 text-left text-xs text-rose-600 shadow-sm">
            {this.state.error.message}
          </pre>
          <button
            onClick={() => this.setState({ error: null })}
            className="rounded-lg bg-blue-600 px-4 py-2 text-xs font-medium text-white transition hover:bg-blue-700"
          >
            重试
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
