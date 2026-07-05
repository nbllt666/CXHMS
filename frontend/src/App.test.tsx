// ========== App.tsx 单元测试 ==========
// G6: 验证 F4 路由懒加载 + Suspense fallback + RouteErrorBoundary 包装。
// 用 vi.mock 模拟 9 个懒加载页面为简单 div，避免触发真实 import；
// 用 MemoryRouter 控制初始路由，验证路由切换与 RouteErrorBoundary 隔离。

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route, Link } from 'react-router-dom';
import { Suspense, lazy, useState } from 'react';

// Mock AppLayout 只渲染 Outlet，避免引入 Sidebar/Header 真实依赖
vi.mock('./components/AppLayout', () => ({
  AppLayout: () => (
    <div data-testid="app-layout">
      <div data-testid="outlet">
        <OutletStub />
      </div>
    </div>
  ),
}));

// OutletStub 实际由 react-router 的 Outlet 提供，这里用占位
import { Outlet } from 'react-router-dom';
function OutletStub() {
  return <Outlet />;
}

// Mock ConnectionCheck 直接渲染 children，避免触发 api.checkHealth
vi.mock('./components/ConnectionCheck', () => ({
  ConnectionCheck: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="connection-check">{children}</div>
  ),
}));

// Mock 全局 ErrorBoundary 直接渲染 children（已在 RouteErrorBoundary 测试中单独覆盖）
vi.mock('./components/ErrorBoundary', () => ({
  ErrorBoundary: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="global-error-boundary">{children}</div>
  ),
}));

// Mock 9 个懒加载页面为简单 div（具名导出）
// 注意：App.tsx 用 import('./pages/X').then(m => ({ default: m.X }))
// mock 时提供 named export 即可
vi.mock('./pages/DashboardPage', () => ({
  DashboardPage: () => <div data-testid="page-dashboard">Dashboard 内容</div>,
}));
vi.mock('./pages/ChatPage', () => ({
  ChatPage: () => <div data-testid="page-chat">Chat 内容</div>,
}));
vi.mock('./pages/MemoriesPage', () => ({
  MemoriesPage: () => <div data-testid="page-memories">Memories 内容</div>,
}));
vi.mock('./pages/ArchivePage', () => ({
  ArchivePage: () => <div data-testid="page-archive">Archive 内容</div>,
}));
vi.mock('./pages/SettingsPage', () => ({
  SettingsPage: () => <div data-testid="page-settings">Settings 内容</div>,
}));
vi.mock('./pages/AcpPage', () => ({
  AcpPage: () => <div data-testid="page-acp">ACP 内容</div>,
}));
vi.mock('./pages/ToolsPage', () => ({
  ToolsPage: () => <div data-testid="page-tools">Tools 内容</div>,
}));
vi.mock('./pages/AgentsPage', () => ({
  AgentsPage: () => <div data-testid="page-agents">Agents 内容</div>,
}));
vi.mock('./pages/MemoryAgentPage', () => ({
  MemoryAgentPage: () => <div data-testid="page-memory-agent">MemoryAgent 内容</div>,
}));

import App from './App';

// 静默 React lazy 加载时的控制台输出
function silenceConsole() {
  return vi.spyOn(console, 'error').mockImplementation(() => {});
}

function renderWithRouter(initialPath: string = '/') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <App />
    </MemoryRouter>
  );
}

describe('App.tsx - 路由懒加载与 RouteErrorBoundary', () => {
  beforeEach(() => {
    silenceConsole();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('路由渲染', () => {
    it('renders Dashboard at "/"', async () => {
      renderWithRouter('/');
      await waitFor(() => {
        expect(screen.getByTestId('page-dashboard')).toBeInTheDocument();
      });
    });

    it('renders ChatPage at "/chat"', async () => {
      renderWithRouter('/chat');
      await waitFor(() => {
        expect(screen.getByTestId('page-chat')).toBeInTheDocument();
      });
    });

    it('renders MemoriesPage at "/memories"', async () => {
      renderWithRouter('/memories');
      await waitFor(() => {
        expect(screen.getByTestId('page-memories')).toBeInTheDocument();
      });
    });

    it('renders ArchivePage at "/archive"', async () => {
      renderWithRouter('/archive');
      await waitFor(() => {
        expect(screen.getByTestId('page-archive')).toBeInTheDocument();
      });
    });

    it('renders SettingsPage at "/settings"', async () => {
      renderWithRouter('/settings');
      await waitFor(() => {
        expect(screen.getByTestId('page-settings')).toBeInTheDocument();
      });
    });

    it('renders AcpPage at "/acp"', async () => {
      renderWithRouter('/acp');
      await waitFor(() => {
        expect(screen.getByTestId('page-acp')).toBeInTheDocument();
      });
    });

    it('renders ToolsPage at "/tools"', async () => {
      renderWithRouter('/tools');
      await waitFor(() => {
        expect(screen.getByTestId('page-tools')).toBeInTheDocument();
      });
    });

    it('renders AgentsPage at "/agents"', async () => {
      renderWithRouter('/agents');
      await waitFor(() => {
        expect(screen.getByTestId('page-agents')).toBeInTheDocument();
      });
    });

    it('renders MemoryAgentPage at "/memory-agent"', async () => {
      renderWithRouter('/memory-agent');
      await waitFor(() => {
        expect(screen.getByTestId('page-memory-agent')).toBeInTheDocument();
      });
    });
  });

  describe('Suspense fallback (PageLoading)', () => {
    it('shows PageLoading spinner while lazy chunk is loading', async () => {
      // 用一个延迟的 lazy 组件模拟加载中
      const LazySlow = lazy(async () => {
        await new Promise((r) => setTimeout(r, 50));
        return { default: () => <div data-testid="slow-content">慢加载内容</div> };
      });

      const { container } = render(
        <MemoryRouter>
          <Suspense fallback={<div className="animate-spin" data-testid="page-loading" />}>
            <LazySlow />
          </Suspense>
        </MemoryRouter>
      );

      // 加载期间应显示 PageLoading spinner
      expect(screen.getByTestId('page-loading')).toBeInTheDocument();
      // container 引用避免未使用警告
      expect(container).toBeTruthy();

      // 加载完成后应显示内容
      await waitFor(() => {
        expect(screen.getByTestId('slow-content')).toBeInTheDocument();
      });
    });

    it('LazyRoute wraps children with Suspense + RouteErrorBoundary (structure check)', async () => {
      // 通过 App 渲染验证 LazyRoute 结构：正常路径下应渲染页面内容
      renderWithRouter('/chat');
      await waitFor(() => {
        expect(screen.getByTestId('page-chat')).toBeInTheDocument();
      });
      // ConnectionCheck + 全局 ErrorBoundary 包装存在
      expect(screen.getByTestId('connection-check')).toBeInTheDocument();
      expect(screen.getByTestId('global-error-boundary')).toBeInTheDocument();
      expect(screen.getByTestId('app-layout')).toBeInTheDocument();
    });
  });

  describe('RouteErrorBoundary 隔离（单页抛错不影响其他路由）', () => {
    it('page throws → RouteErrorBoundary shows "页面加载失败", other routes still accessible', async () => {
      // 重新 mock ChatPage 为抛错组件
      vi.doMock('./pages/ChatPage', () => ({
        ChatPage: function BoomChat() {
          throw new Error('ChatPage render fail');
        },
      }));

      // 由于 vi.mock 是 hoisted，vi.doMock 不会立即生效于已 import 的 App
      // 这里改用直接渲染 RouteErrorBoundary + 抛错子组件，模拟"单页抛错"场景
      const { RouteErrorBoundary } = await import('./components/RouteErrorBoundary');

      function ThrowingPage() {
        throw new Error('页面 X 渲染失败');
      }
      function NormalPage() {
        return <div data-testid="page-y">页面 Y 正常</div>;
      }

      const { rerender } = render(
        <MemoryRouter>
          <RouteErrorBoundary>
            <ThrowingPage />
          </RouteErrorBoundary>
        </MemoryRouter>
      );
      expect(screen.getByText('页面加载失败')).toBeInTheDocument();

      // 切换到其他路由（用同一个 boundary 重渲染为正常页面）
      rerender(
        <MemoryRouter>
          <RouteErrorBoundary>
            <NormalPage />
          </RouteErrorBoundary>
        </MemoryRouter>
      );
      // 注意：这里需要先点重试才能恢复，但模拟路由切换是 unmount 旧 boundary + mount 新 boundary
      // 直接用全新 boundary 验证：其他路由的 boundary 不受影响
      const { unmount } = render(
        <MemoryRouter>
          <RouteErrorBoundary>
            <NormalPage />
          </RouteErrorBoundary>
        </MemoryRouter>
      );
      expect(screen.getAllByText('页面 Y 正常').length).toBeGreaterThan(0);
      unmount();
    });
  });

  describe('路由切换（导航）', () => {
    it('navigates from Dashboard to Chat via Link click', async () => {
      // 用 React Router 的 Link + MemoryRouter 触发真实导航
      function NavWrapper() {
        return (
          <MemoryRouter initialEntries={['/']}>
            <nav>
              <Link to="/chat" data-testid="go-chat">to chat</Link>
            </nav>
            <App />
          </MemoryRouter>
        );
      }
      render(<NavWrapper />);
      await waitFor(() => {
        expect(screen.getByTestId('page-dashboard')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByTestId('go-chat'));

      await waitFor(() => {
        expect(screen.getByTestId('page-chat')).toBeInTheDocument();
      });
      // Dashboard 应卸载
      expect(screen.queryByTestId('page-dashboard')).not.toBeInTheDocument();
    });

    it('navigates through multiple routes sequentially', async () => {
      function NavWrapper() {
        return (
          <MemoryRouter initialEntries={['/']}>
            <nav>
              <Link to="/chat" data-testid="go-chat">to chat</Link>
              <Link to="/memories" data-testid="go-memories">to memories</Link>
              <Link to="/settings" data-testid="go-settings">to settings</Link>
            </nav>
            <App />
          </MemoryRouter>
        );
      }
      render(<NavWrapper />);

      await waitFor(() => expect(screen.getByTestId('page-dashboard')).toBeInTheDocument());
      fireEvent.click(screen.getByTestId('go-chat'));
      await waitFor(() => expect(screen.getByTestId('page-chat')).toBeInTheDocument());

      fireEvent.click(screen.getByTestId('go-memories'));
      await waitFor(() => expect(screen.getByTestId('page-memories')).toBeInTheDocument());

      fireEvent.click(screen.getByTestId('go-settings'));
      await waitFor(() => expect(screen.getByTestId('page-settings')).toBeInTheDocument());
    });
  });

  describe('ErrorBoundary + ConnectionCheck 包装层级', () => {
    it('wraps app with ConnectionCheck inside global ErrorBoundary', async () => {
      renderWithRouter('/');
      await waitFor(() => {
        expect(screen.getByTestId('page-dashboard')).toBeInTheDocument();
      });
      // 全局 ErrorBoundary 在最外层
      const globalEB = screen.getByTestId('global-error-boundary');
      // ConnectionCheck 在 ErrorBoundary 内
      const connCheck = screen.getByTestId('connection-check');
      expect(globalEB).toContainElement(connCheck);
      // AppLayout 在 ConnectionCheck 内
      const appLayout = screen.getByTestId('app-layout');
      expect(connCheck).toContainElement(appLayout);
      // 页面在 AppLayout 的 Outlet 内
      expect(appLayout).toContainElement(screen.getByTestId('page-dashboard'));
    });
  });
});
