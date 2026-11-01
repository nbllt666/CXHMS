// ========== KnowledgePage 集成测试 ==========
// 覆盖：页面渲染与空态、上传回调（FormData 字段 + invalidate 触发重新拉取）、
// 删除文档二次确认调用 deleteDocument、切换 agent 后的查询参数。
//
// Mock 策略：mock ../api 的 api.getAgents 与 ../api/knowledge 的 knowledgeApi；
// 使用真实 @tanstack/react-query（QueryClientProvider 包裹），retry=false 避免重试等待。

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mockGetAgents = vi.fn();
const mockUploadDocument = vi.fn();
const mockCreateEntry = vi.fn();
const mockListItems = vi.fn();
const mockGetItem = vi.fn();
const mockDeleteItem = vi.fn();
const mockSearch = vi.fn();
const mockListDocuments = vi.fn();
const mockGetDocument = vi.fn();
const mockDeleteDocument = vi.fn();
const mockGetHealth = vi.fn();

vi.mock('../api', () => ({
  api: {
    getAgents: (...args: unknown[]) => mockGetAgents(...args),
  },
}));

vi.mock('../api/knowledge', () => ({
  knowledgeApi: {
    uploadDocument: (...args: unknown[]) => mockUploadDocument(...args),
    createEntry: (...args: unknown[]) => mockCreateEntry(...args),
    listItems: (...args: unknown[]) => mockListItems(...args),
    getItem: (...args: unknown[]) => mockGetItem(...args),
    deleteItem: (...args: unknown[]) => mockDeleteItem(...args),
    search: (...args: unknown[]) => mockSearch(...args),
    listDocuments: (...args: unknown[]) => mockListDocuments(...args),
    getDocument: (...args: unknown[]) => mockGetDocument(...args),
    deleteDocument: (...args: unknown[]) => mockDeleteDocument(...args),
    getHealth: (...args: unknown[]) => mockGetHealth(...args),
  },
}));

// ---------- Import after mocks ----------
import { KnowledgePage } from './KnowledgePage';

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <KnowledgePage />
    </QueryClientProvider>
  );
}

const documentFixture = {
  document_id: 'doc-1',
  agent_id: 'default',
  filename: '说明文档.txt',
  mime: 'text/plain',
  size_bytes: 1024,
  parse_status: 'parsed' as const,
  parse_error: null,
  created_at: '2026-11-01T10:00:00Z',
};

describe('KnowledgePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    mockGetAgents.mockResolvedValue({
      agents: [
        { id: 'default', name: '默认' },
        { id: 'agent-2', name: '助理二号' },
      ],
    });
    mockListDocuments.mockResolvedValue({ documents: [], total: 0 });
    mockListItems.mockResolvedValue({ items: [], total: 0 });
    mockSearch.mockResolvedValue({ hits: [], total: 0 });
    mockGetDocument.mockResolvedValue({
      ...documentFixture,
      text_preview: '预览文本',
      chunk_count: 2,
    });
    mockDeleteDocument.mockResolvedValue({ success: true });
    mockDeleteItem.mockResolvedValue({ success: true });
    mockUploadDocument.mockResolvedValue({
      document_id: 'doc-uploaded',
      parse_status: 'pending',
      deduplicated: false,
    });

    vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.spyOn(window, 'alert').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('渲染页面结构并展示文档/条目空态', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('知识库')).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(
        screen.getByText('还没有上传任何文档，可从上方拖拽或选择文件上传。')
      ).toBeInTheDocument();
      expect(
        screen.getByText('暂无知识条目，上传文档解析完成后将自动分块入库。')
      ).toBeInTheDocument();
    });
    expect(mockListDocuments).toHaveBeenCalledWith({ agent_id: 'default', limit: 100 });
  });

  it('上传文件时携带 agent_id/tags 并触发列表刷新', async () => {
    renderPage();

    const fileInput = await screen.findByTestId('knowledge-file-input');
    await waitFor(() => {
      expect(mockListDocuments).toHaveBeenCalledTimes(1);
    });

    const file = new File(['hello'], 'test.txt', { type: 'text/plain' });
    fireEvent.change(fileInput, { target: { files: [file] } });
    fireEvent.change(screen.getByPlaceholderText('例如：项目资料, 会议纪要'), {
      target: { value: '项目资料, 重要' },
    });

    fireEvent.click(screen.getByText('开始上传'));

    await waitFor(() => {
      expect(mockUploadDocument).toHaveBeenCalledTimes(1);
    });

    const formData = mockUploadDocument.mock.calls[0][0] as FormData;
    expect(formData.get('agent_id')).toBe('default');
    expect(JSON.parse(String(formData.get('tags')))).toEqual(['项目资料', '重要']);
    expect(formData.get('file')).toBe(file);

    // 上传成功后页面 invalidate 文档列表 → 重新拉取
    await waitFor(() => {
      expect(mockListDocuments).toHaveBeenCalledTimes(2);
    });
  });

  it('删除文档需二次确认并调用 deleteDocument', async () => {
    mockListDocuments.mockResolvedValue({ documents: [documentFixture], total: 1 });
    renderPage();

    const deleteButton = await screen.findByTestId('delete-document-doc-1');
    fireEvent.click(deleteButton);

    expect(window.confirm).toHaveBeenCalledTimes(1);
    await waitFor(() => {
      expect(mockDeleteDocument).toHaveBeenCalledWith('doc-1', 'default');
    });
  });

  it('切换 agent 后以新的 agent_id 重新查询文档与条目', async () => {
    renderPage();

    await waitFor(() => {
      expect(mockListDocuments).toHaveBeenCalledWith({ agent_id: 'default', limit: 100 });
    });

    // 等待 agent 选项加载完成（否则 select 赋值会被 jsdom 丢弃为空字符串）
    await screen.findByRole('option', { name: '助理二号' });

    fireEvent.change(screen.getByLabelText('选择 agent'), { target: { value: 'agent-2' } });

    await waitFor(() => {
      expect(mockListDocuments).toHaveBeenCalledWith({ agent_id: 'agent-2', limit: 100 });
    });
    await waitFor(() => {
      expect(mockListItems).toHaveBeenCalledWith(
        expect.objectContaining({ agent_id: 'agent-2' })
      );
    });
  });
});
