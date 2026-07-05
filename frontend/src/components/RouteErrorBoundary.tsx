import { Component, ErrorInfo, ReactNode } from 'react';
import { AlertCircle, RefreshCw } from 'lucide-react';

// F5: 路由级 ErrorBoundary。
// 与全局 ErrorBoundary 区别：fallback 仅占据路由出口区域（非全屏），
// 单页抛错时其他路由仍可正常访问与导航。

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class RouteErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('RouteErrorBoundary caught an error:', error, errorInfo);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center min-h-[60vh] p-8 text-center">
          <AlertCircle className="w-12 h-12 mb-4" style={{ color: 'var(--color-error)' }} />
          <h2 className="text-xl font-semibold mb-2" style={{ color: 'var(--color-text-primary)' }}>
            页面加载失败
          </h2>
          <p className="mb-4" style={{ color: 'var(--color-text-secondary)' }}>
            该页面遇到了错误，其他页面仍可正常访问。
          </p>
          {this.state.error && (
            <pre
              className="max-w-lg w-full text-xs text-left p-3 rounded-[var(--radius-md)] overflow-auto max-h-40 mb-4"
              style={{
                backgroundColor: 'var(--color-bg-tertiary)',
                color: 'var(--color-text-secondary)',
              }}
            >
              {this.state.error.message}
            </pre>
          )}
          <div className="flex gap-3">
            <button
              onClick={() => window.location.reload()}
              className="flex items-center gap-2 px-4 py-2 rounded-[var(--radius-md)] hover:opacity-90 transition-opacity"
              style={{
                backgroundColor: 'var(--color-primary)',
                color: 'var(--color-primary-foreground)',
              }}
            >
              <RefreshCw className="w-4 h-4" />
              刷新页面
            </button>
            <button
              onClick={this.handleReset}
              className="px-4 py-2 rounded-[var(--radius-md)] transition-colors"
              style={{
                border: '1px solid var(--color-border)',
                color: 'var(--color-text-primary)',
              }}
            >
              重试
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
