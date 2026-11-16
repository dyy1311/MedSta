import { Component, type ErrorInfo, type ReactNode } from "react";
import { RefreshCw, TriangleAlert } from "lucide-react";

interface Props {
  children: ReactNode;
  /** 可注入 fallback（测试用）；缺省渲染标准错误卡 */
  fallback?: (error: Error, reload: () => void) => ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * 渲染错误边界（039）：子树崩溃时显示可恢复的错误卡而非白屏。
 * reload 保留应用状态下的整页刷新（React 状态不可恢复时唯一可靠手段）。
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("界面渲染异常", error, info.componentStack);
  }

  render(): ReactNode {
    const { error } = this.state;
    if (error) {
      if (this.props.fallback) return this.props.fallback(error, () => window.location.reload());
      return (
        <div className="flex h-full items-center justify-center bg-surface-page p-6">
          <div
            data-testid="error-boundary"
            className="w-full max-w-md space-y-3 rounded-2xl bg-surface-card p-6 text-center shadow-card"
          >
            <TriangleAlert className="mx-auto h-8 w-8 text-warn" />
            <h1 className="text-base font-semibold text-ink">界面出现异常</h1>
            <p className="text-xs text-ink-muted">
              渲染过程遇到未预期的错误。你的数据与会话保存在服务端，不会丢失。
            </p>
            <pre className="max-h-24 overflow-auto rounded-lg bg-primary-dark/95 p-2 text-left text-[11px] text-primary-cyan">
              {String(error.message || error)}
            </pre>
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="inline-flex cursor-pointer items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-primary-hover"
            >
              <RefreshCw className="h-4 w-4" />
              重新加载
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
