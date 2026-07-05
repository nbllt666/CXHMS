import React, { Suspense } from 'react';
import { Routes, Route } from 'react-router-dom';
import { AppLayout } from './components/AppLayout';
import { ErrorBoundary } from './components/ErrorBoundary';
import { RouteErrorBoundary } from './components/RouteErrorBoundary';
import { ConnectionCheck } from './components/ConnectionCheck';

// F4: 路由懒加载，按页面拆分 chunk，降低首屏 bundle。
// 各页面为具名导出，需映射为 { default } 以适配 React.lazy。
const DashboardPage = React.lazy(() =>
  import('./pages/DashboardPage').then((m) => ({ default: m.DashboardPage }))
);
const ChatPage = React.lazy(() =>
  import('./pages/ChatPage').then((m) => ({ default: m.ChatPage }))
);
const MemoriesPage = React.lazy(() =>
  import('./pages/MemoriesPage').then((m) => ({ default: m.MemoriesPage }))
);
const ArchivePage = React.lazy(() =>
  import('./pages/ArchivePage').then((m) => ({ default: m.ArchivePage }))
);
const SettingsPage = React.lazy(() =>
  import('./pages/SettingsPage').then((m) => ({ default: m.SettingsPage }))
);
const AcpPage = React.lazy(() =>
  import('./pages/AcpPage').then((m) => ({ default: m.AcpPage }))
);
const ToolsPage = React.lazy(() =>
  import('./pages/ToolsPage').then((m) => ({ default: m.ToolsPage }))
);
const AgentsPage = React.lazy(() =>
  import('./pages/AgentsPage').then((m) => ({ default: m.AgentsPage }))
);
const MemoryAgentPage = React.lazy(() =>
  import('./pages/MemoryAgentPage').then((m) => ({ default: m.MemoryAgentPage }))
);

/** 路由懒加载占位 */
function PageLoading() {
  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div
        className="animate-spin rounded-full h-10 w-10"
        style={{ border: '2px solid var(--color-border)', borderBottomColor: 'var(--color-primary)' }}
      />
    </div>
  );
}

/**
 * 每个路由的统一包装：Suspense（懒加载占位）+ RouteErrorBoundary（单页抛错隔离）。
 * 单页抛错时只影响该路由出口，其他路由仍可访问。
 */
function LazyRoute({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={<PageLoading />}>
      <RouteErrorBoundary>{children}</RouteErrorBoundary>
    </Suspense>
  );
}

function App() {
  return (
    <ErrorBoundary>
      <ConnectionCheck>
        <Routes>
          <Route path="/" element={<AppLayout />}>
            <Route
              index
              element={
                <LazyRoute>
                  <DashboardPage />
                </LazyRoute>
              }
            />
            <Route
              path="chat"
              element={
                <LazyRoute>
                  <ChatPage />
                </LazyRoute>
              }
            />
            <Route
              path="memories"
              element={
                <LazyRoute>
                  <MemoriesPage />
                </LazyRoute>
              }
            />
            <Route
              path="archive"
              element={
                <LazyRoute>
                  <ArchivePage />
                </LazyRoute>
              }
            />
            <Route
              path="agents"
              element={
                <LazyRoute>
                  <AgentsPage />
                </LazyRoute>
              }
            />
            <Route
              path="acp"
              element={
                <LazyRoute>
                  <AcpPage />
                </LazyRoute>
              }
            />
            <Route
              path="tools"
              element={
                <LazyRoute>
                  <ToolsPage />
                </LazyRoute>
              }
            />
            <Route
              path="settings"
              element={
                <LazyRoute>
                  <SettingsPage />
                </LazyRoute>
              }
            />
            <Route
              path="memory-agent"
              element={
                <LazyRoute>
                  <MemoryAgentPage />
                </LazyRoute>
              }
            />
          </Route>
        </Routes>
      </ConnectionCheck>
    </ErrorBoundary>
  );
}

export default App;
