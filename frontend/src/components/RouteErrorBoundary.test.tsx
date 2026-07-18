// ========== RouteErrorBoundary 单元测试 ==========
// G6: 验证 F5 路由级 ErrorBoundary——单页抛错时仅该路由出口显示 fallback，
// 其他路由仍可访问。与全局 ErrorBoundary 区别：fallback 不全屏。

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { RouteErrorBoundary } from './RouteErrorBoundary';

// 子组件渲染时抛错（用于触发 ErrorBoundary）
function BoomComponent({ message = 'boom' }: { message?: string }): React.ReactElement {
  throw new Error(message);
}

// 静默 React 在 jsdom 下抛错时的控制台输出，避免污染测试输出
function silenceConsole() {
  const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
  return spy;
}

describe('RouteErrorBoundary', () => {
  beforeEach(() => {
    vi.spyOn(window, 'location', 'get').mockReturnValue({
      ...window.location,
      reload: vi.fn(),
    } as unknown as Location);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders children when no error', () => {
    const spy = silenceConsole();
    render(
      <RouteErrorBoundary>
        <div>正常内容</div>
      </RouteErrorBoundary>
    );
    expect(screen.getByText('正常内容')).toBeInTheDocument();
    spy.mockRestore();
  });

  it('renders fallback with "页面加载失败" when child throws', () => {
    const spy = silenceConsole();
    render(
      <RouteErrorBoundary>
        <BoomComponent message="something broke" />
      </RouteErrorBoundary>
    );
    expect(screen.getByText('页面加载失败')).toBeInTheDocument();
    expect(screen.getByText('该页面遇到了错误，其他页面仍可正常访问。')).toBeInTheDocument();
    // 错误信息展示
    expect(screen.getByText('something broke')).toBeInTheDocument();
    spy.mockRestore();
  });

  it('shows both "刷新页面" and "重试" buttons', () => {
    const spy = silenceConsole();
    render(
      <RouteErrorBoundary>
        <BoomComponent />
      </RouteErrorBoundary>
    );
    expect(screen.getByRole('button', { name: /刷新页面/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /重试/ })).toBeInTheDocument();
    spy.mockRestore();
  });

  it('calls window.location.reload when "刷新页面" clicked', () => {
    const spy = silenceConsole();
    const reloadMock = window.location.reload as ReturnType<typeof vi.fn>;
    render(
      <RouteErrorBoundary>
        <BoomComponent />
      </RouteErrorBoundary>
    );
    fireEvent.click(screen.getByRole('button', { name: /刷新页面/ }));
    expect(reloadMock).toHaveBeenCalledTimes(1);
    spy.mockRestore();
  });

  it('resets error state when "重试" clicked (child no longer throws after reset)', () => {
    const spy = silenceConsole();
    // 初始抛错；点击重试前先把 shouldThrow 切到 false，模拟"问题已修复后重试"
    let shouldThrow = true;
    function ToggleComponent() {
      if (shouldThrow) throw new Error('first render fail');
      return <div>恢复后内容</div>;
    }
    render(
      <RouteErrorBoundary>
        <ToggleComponent />
      </RouteErrorBoundary>
    );
    expect(screen.getByText('页面加载失败')).toBeInTheDocument();

    // 在点击重试前切到不抛错，重试按钮触发 setState 后重渲染 ToggleComponent 不再抛错
    shouldThrow = false;
    fireEvent.click(screen.getByRole('button', { name: /重试/ }));

    expect(screen.getByText('恢复后内容')).toBeInTheDocument();
    expect(screen.queryByText('页面加载失败')).not.toBeInTheDocument();
    spy.mockRestore();
  });

  it('re-throws fallback if child still errors after "重试" clicked', () => {
    const spy = silenceConsole();
    // 重试后子组件仍然抛错 → fallback 重新显示（验证重试机制不会吞错）
    function AlwaysBoomComponent(): React.ReactElement {
      throw new Error('persistent fail');
    }
    render(
      <RouteErrorBoundary>
        <AlwaysBoomComponent />
      </RouteErrorBoundary>
    );
    expect(screen.getByText('页面加载失败')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /重试/ }));
    // 仍抛错 → fallback 再次显示，错误信息更新
    expect(screen.getByText('页面加载失败')).toBeInTheDocument();
    expect(screen.getByText('persistent fail')).toBeInTheDocument();
    spy.mockRestore();
  });

  it('logs error to console via componentDidCatch', () => {
    const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    render(
      <RouteErrorBoundary>
        <BoomComponent message="logged error" />
      </RouteErrorBoundary>
    );
    // componentDidCatch 调用 console.error，消息含 "RouteErrorBoundary caught an error"
    expect(errSpy).toHaveBeenCalled();
    const calls = errSpy.mock.calls.map((c) => String(c[0]));
    expect(calls.some((s) => s.includes('RouteErrorBoundary caught an error'))).toBe(true);
    errSpy.mockRestore();
  });

  it('isolates errors: only this boundary shows fallback, sibling subtrees unaffected', () => {
    const spy = silenceConsole();
    // 模拟"其他路由"：并排渲染一个 RouteErrorBoundary 包裹的抛错组件 + 一个正常 sibling
    render(
      <div>
        <RouteErrorBoundary>
          <BoomComponent message="boundary failure" />
        </RouteErrorBoundary>
        <div>兄弟路由仍可访问</div>
      </div>
    );
    // 抛错边界显示 fallback
    expect(screen.getByText('页面加载失败')).toBeInTheDocument();
    // sibling 未受影响
    expect(screen.getByText('兄弟路由仍可访问')).toBeInTheDocument();
    spy.mockRestore();
  });
});
