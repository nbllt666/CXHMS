// ========== SettingsPage 重新初始化功能单元测试 ==========
// Task 8.5 — 覆盖重新初始化按钮的 4 个用例：
//   1. test_reinit_button_exists：按钮渲染存在
//   2. test_reinit_confirm_dialog：点击后弹出确认对话框
//   3. test_reinit_cancel：点击取消关闭对话框
//   4. test_reinit_api_call：点击确认触发 api.reinitComponents
//
// Mock 策略：react-i18next / @tanstack/react-query / ../api / ../store/themeStore /
// ../components/ui / ../components/layout。useMutation 的 mutationFn 被捕获后由
// mock mutate 直接调用，使 api.reinitComponents 可被验证。

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';

// ---------- Mock i18n ----------
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'zh-CN' },
  }),
}));

// ---------- Mock useThemeStore ----------
vi.mock('../store/themeStore', () => ({
  useThemeStore: () => ({
    theme: 'light',
    setTheme: vi.fn(),
    toggleTheme: vi.fn(),
  }),
}));

// ---------- Mock ../lib/utils (cn) ----------
vi.mock('../lib/utils', () => ({
  cn: (...args: Array<unknown>) => args.filter(Boolean).join(' '),
}));

// ---------- Mock ../components/ui ----------
vi.mock('../components/ui', () => ({
  Button: ({
    children,
    onClick,
    disabled,
    loading,
    icon,
    ...rest
  }: {
    children?: ReactNode;
    onClick?: () => void;
    disabled?: boolean;
    loading?: boolean;
    icon?: ReactNode;
    [key: string]: unknown;
  }) => (
    <button
      onClick={onClick}
      disabled={disabled || loading}
      data-testid={typeof children === 'string' ? `btn-${children}` : 'btn'}
      {...rest}
    >
      {icon}
      {children}
    </button>
  ),
  Card: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  CardBody: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
}));

// ---------- Mock ../components/layout (PageHeader) ----------
vi.mock('../components/layout', () => ({
  PageHeader: ({
    title,
    description,
    actions,
  }: {
    title: string;
    description?: string;
    actions?: ReactNode;
  }) => (
    <div data-testid="page-header">
      <h1>{title}</h1>
      {description && <p>{description}</p>}
      {actions && <div data-testid="header-actions">{actions}</div>}
    </div>
  ),
}));

// ---------- Mock ../api ----------
const mockReinitComponents = vi.fn();
const mockGetReinitStatus = vi.fn();
const mockGetMainBackendStatus = vi.fn();
const mockGetServiceConfig = vi.fn();
const mockUpdateServiceConfig = vi.fn();

vi.mock('../api', () => ({
  api: {
    getMainBackendStatus: (...args: unknown[]) => mockGetMainBackendStatus(...args),
    getServiceConfig: (...args: unknown[]) => mockGetServiceConfig(...args),
    updateServiceConfig: (...args: unknown[]) => mockUpdateServiceConfig(...args),
    reinitComponents: (...args: unknown[]) => mockReinitComponents(...args),
    getReinitStatus: (...args: unknown[]) => mockGetReinitStatus(...args),
  },
}));

// ---------- Mock @tanstack/react-query ----------
// useQuery 返回空数据避免 serviceConfig 触发副作用；
// useMutation 捕获 mutationFn 使测试可验证 api.reinitComponents 被调用。
const mutationHolder = vi.hoisted(() => ({
  mutationFn: null as ((args?: unknown) => Promise<unknown>) | null,
  isPending: false,
}));

vi.mock('@tanstack/react-query', () => ({
  useQuery: vi.fn(() => ({ data: undefined, isLoading: false })),
  useMutation: (options: {
    mutationFn: (args?: unknown) => Promise<unknown>;
    onSuccess?: (data: unknown) => void;
    onError?: (error: unknown) => void;
  }) => {
    mutationHolder.mutationFn = options.mutationFn;
    return {
      mutate: (args?: unknown) => {
        // 调用捕获的 mutationFn → 内部调用 api.reinitComponents
        const result = mutationHolder.mutationFn?.(args);
        if (result && typeof result.then === 'function') {
          result.then(options.onSuccess).catch(options.onError);
        }
      },
      isPending: mutationHolder.isPending,
      isError: false,
      isSuccess: false,
    };
  },
  useQueryClient: vi.fn(() => ({ invalidateQueries: vi.fn() })),
}));

// ---------- Import after mocks ----------
import { SettingsPage } from './SettingsPage';

describe('SettingsPage - 重新初始化按钮', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(window, 'alert').mockImplementation(() => {});
    vi.spyOn(window, 'confirm').mockImplementation(() => true);

    mockGetMainBackendStatus.mockResolvedValue({ running: true });
    mockGetServiceConfig.mockResolvedValue({ config: {} });
    mockReinitComponents.mockResolvedValue({
      status: 'accepted',
      task_id: 'task-test-1',
      estimated_components: ['model_router', 'llm_client'],
    });
    mockGetReinitStatus.mockResolvedValue({ status: 'idle' });
    mutationHolder.mutationFn = null;
    mutationHolder.isPending = false;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // 用例 1：按钮渲染存在
  it('test_reinit_button_exists', async () => {
    render(<SettingsPage />);

    // 等待后端状态检查完成（按钮 disabled 依赖 isBackendRunning）
    await waitFor(() => {
      expect(mockGetMainBackendStatus).toHaveBeenCalled();
    });

    // 重新初始化按钮存在于 PageHeader actions 中
    const reinitButton = screen.getByText('重新初始化');
    expect(reinitButton).toBeInTheDocument();
    expect(reinitButton.tagName).toBe('BUTTON');
  });

  // 用例 2：点击后弹出确认对话框
  it('test_reinit_confirm_dialog', async () => {
    render(<SettingsPage />);

    await waitFor(() => {
      expect(mockGetMainBackendStatus).toHaveBeenCalled();
    });

    // 点击重新初始化按钮
    const reinitButton = screen.getByText('重新初始化');
    fireEvent.click(reinitButton);

    // 确认对话框出现（用描述文本验证，避免与按钮文本重复）
    await waitFor(() => {
      expect(screen.getByText(/这将重初始化以下组件/)).toBeInTheDocument();
    });
    // 标题与按钮均含 "确认重新初始化" — 应有 2 个匹配
    expect(screen.getAllByText('确认重新初始化').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('取消')).toBeInTheDocument();
  });

  // 用例 3：点击取消关闭对话框
  it('test_reinit_cancel', async () => {
    render(<SettingsPage />);

    await waitFor(() => {
      expect(mockGetMainBackendStatus).toHaveBeenCalled();
    });

    // 打开对话框
    fireEvent.click(screen.getByText('重新初始化'));
    await waitFor(() => {
      expect(screen.getByText(/这将重初始化以下组件/)).toBeInTheDocument();
    });

    // 点击取消
    fireEvent.click(screen.getByText('取消'));

    // 对话框关闭（描述文本不再可见）
    await waitFor(() => {
      expect(screen.queryByText(/这将重初始化以下组件/)).not.toBeInTheDocument();
    });
    // 按钮与标题也应消失
    expect(screen.queryAllByText('确认重新初始化')).toHaveLength(0);
  });

  // 用例 4：点击确认触发 api.reinitComponents
  it('test_reinit_api_call', async () => {
    render(<SettingsPage />);

    await waitFor(() => {
      expect(mockGetMainBackendStatus).toHaveBeenCalled();
    });

    // 打开对话框
    fireEvent.click(screen.getByText('重新初始化'));
    await waitFor(() => {
      expect(screen.getByText(/这将重初始化以下组件/)).toBeInTheDocument();
    });

    // 点击确认按钮 — 用 getByRole 精确定位按钮（避免与 h3 标题冲突）
    const confirmButton = screen.getByRole('button', { name: '确认重新初始化' });
    fireEvent.click(confirmButton);

    // 验证 api.reinitComponents 被调用
    await waitFor(() => {
      expect(mockReinitComponents).toHaveBeenCalled();
    });
  });
});
