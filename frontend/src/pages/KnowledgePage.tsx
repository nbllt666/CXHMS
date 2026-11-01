import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../api';
import { knowledgeApi } from '../api/knowledge';
import type { KnowledgeDocument, KnowledgeItem } from '../api/knowledge';
import { PageHeader } from '../components/layout';
import { Badge, Button, Card, CardBody, Input } from '../components/ui';
import { KnowledgeUploadPanel } from '../components/knowledge/KnowledgeUploadPanel';
import { KnowledgeItemCard } from '../components/knowledge/KnowledgeItemCard';
import { KnowledgeDetailDrawer } from '../components/knowledge/KnowledgeDetailDrawer';
import { formatDate, truncate } from '../lib/utils';

type ItemTypeFilter = 'all' | 'doc_chunk' | 'experience';

interface AgentOption {
  id: string;
  name: string;
}

const documentStatusLabels: Record<KnowledgeDocument['parse_status'], string> = {
  pending: '等待解析',
  parsing: '解析中',
  parsed: '解析完成',
  failed: '解析失败',
  unsupported: '不支持',
};

const documentStatusVariants: Record<
  KnowledgeDocument['parse_status'],
  'success' | 'warning' | 'info' | 'error' | 'secondary'
> = {
  pending: 'warning',
  parsing: 'info',
  parsed: 'success',
  failed: 'error',
  unsupported: 'secondary',
};

/** 兼容 agents 返回值中的 agent_id / id 字段；同时兼容数组与 { agents: [] } 两种形态 */
function toAgentOptions(data: unknown): AgentOption[] {
  const raw = Array.isArray(data)
    ? data
    : Array.isArray((data as { agents?: unknown })?.agents)
      ? ((data as { agents: unknown[] }).agents ?? [])
      : [];
  return raw
    .map((entry) => {
      const record = entry as Record<string, unknown>;
      const id = String(record?.id ?? record?.agent_id ?? '');
      return { id, name: String(record?.name ?? id) };
    })
    .filter((agent) => agent.id.length > 0);
}

function isParsing(status: KnowledgeDocument['parse_status']): boolean {
  return status === 'pending' || status === 'parsing';
}

/**
 * 独立知识库页面：agent 隔离选择、上传、检索、文档状态轮询、条目列表与详情、删除。
 */
export function KnowledgePage() {
  const queryClient = useQueryClient();

  const [currentAgentId, setCurrentAgentId] = useState('default');
  const [searchQuery, setSearchQuery] = useState('');
  const [itemTypeFilter, setItemTypeFilter] = useState<ItemTypeFilter>('all');
  const [tagFilter, setTagFilter] = useState('');
  const [selectedItem, setSelectedItem] = useState<KnowledgeItem | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);

  const searchText = searchQuery.trim();
  const tagText = tagFilter.trim();

  const { data: agentsData } = useQuery({
    queryKey: ['agents-for-knowledge'],
    queryFn: () => api.getAgents(),
    staleTime: 60000,
  });
  const agentOptions = toAgentOptions(agentsData);

  const documentsQuery = useQuery({
    queryKey: ['knowledge-documents', currentAgentId],
    queryFn: () =>
      knowledgeApi.listDocuments({ agent_id: currentAgentId, limit: 100 }),
    refetchInterval: (query) => {
      const docs = query.state.data?.documents;
      return docs?.some((doc) => isParsing(doc.parse_status)) ? 3000 : false;
    },
  });

  const itemsQuery = useQuery({
    queryKey: ['knowledge-items', currentAgentId, itemTypeFilter, tagText, searchText],
    queryFn: async (): Promise<{
      items: KnowledgeItem[];
      scores: Record<string, number>;
    }> => {
      if (searchText) {
        const result = await knowledgeApi.search({
          agent_id: currentAgentId,
          query: searchText,
          top_k: 50,
          tags: tagText ? [tagText] : undefined,
          item_type: itemTypeFilter === 'all' ? undefined : itemTypeFilter,
        });
        const scores: Record<string, number> = {};
        result.hits.forEach((hit) => {
          scores[hit.item_id] = hit.score;
        });
        return { items: result.hits, scores };
      }

      const result = await knowledgeApi.listItems({
        agent_id: currentAgentId,
        item_type: itemTypeFilter === 'all' ? undefined : itemTypeFilter,
        tags: tagText || undefined,
        limit: 50,
      });
      return { items: result.items, scores: {} };
    },
  });

  const selectedDocumentId = selectedItem?.document_id ?? undefined;
  const documentQuery = useQuery({
    queryKey: ['knowledge-document-detail', currentAgentId, selectedDocumentId],
    queryFn: () => knowledgeApi.getDocument(selectedDocumentId as string, currentAgentId),
    enabled: Boolean(selectedDocumentId) && detailOpen,
  });

  const invalidateKnowledge = () => {
    queryClient.invalidateQueries({ queryKey: ['knowledge-documents', currentAgentId] });
    queryClient.invalidateQueries({ queryKey: ['knowledge-items', currentAgentId] });
    queryClient.invalidateQueries({
      queryKey: ['knowledge-document-detail', currentAgentId],
    });
  };

  const handleDeleteItem = async (item: KnowledgeItem) => {
    const label = item.title || truncate(item.content, 20);
    if (!window.confirm(`确认删除条目「${label}」？删除后将从检索结果中消失。`)) return;
    try {
      await knowledgeApi.deleteItem(item.item_id, currentAgentId);
      if (selectedItem?.item_id === item.item_id) {
        setDetailOpen(false);
        setSelectedItem(null);
      }
      invalidateKnowledge();
    } catch {
      window.alert('删除条目失败，请稍后重试。');
    }
  };

  const handleDeleteDocument = async (document: KnowledgeDocument) => {
    if (
      !window.confirm(
        `确认删除文档「${document.filename}」？其分块、向量与物理文件将一并删除。`
      )
    ) {
      return;
    }
    try {
      await knowledgeApi.deleteDocument(document.document_id, currentAgentId);
      invalidateKnowledge();
    } catch {
      window.alert('删除文档失败，请稍后重试。');
    }
  };

  const documents = documentsQuery.data?.documents ?? [];
  const items = itemsQuery.data?.items ?? [];
  const scores = itemsQuery.data?.scores ?? {};

  return (
    <div className="max-w-6xl mx-auto">
      <PageHeader
        title="知识库"
        description="独立知识库：上传文档自动解析，检索知识条目，沉淀可复用经验。"
        actions={
          <div className="flex items-center gap-2">
            <span className="text-sm text-[var(--color-text-secondary)]">Agent：</span>
            <select
              aria-label="选择 agent"
              value={currentAgentId}
              onChange={(event) => {
                setCurrentAgentId(event.target.value);
                setSelectedItem(null);
                setDetailOpen(false);
              }}
              className="px-3 py-2 bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-[var(--radius-md)] text-sm"
            >
              <option value="default">默认（default）</option>
              {agentOptions
                .filter((agent) => agent.id !== 'default')
                .map((agent) => (
                  <option key={agent.id} value={agent.id}>
                    {agent.name || agent.id}
                  </option>
                ))}
            </select>
          </div>
        }
      />

      <KnowledgeUploadPanel agentId={currentAgentId} onUploaded={invalidateKnowledge} />

      {/* 检索与过滤 */}
      <Card className="mb-6">
        <CardBody>
          <div className="flex flex-col md:flex-row md:items-end gap-3">
            <div className="flex-1">
              <Input
                label="关键词检索"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder="输入关键词，内容命中走混合检索；留空则显示条目列表"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-[var(--color-text-secondary)] mb-1.5">
                条目类型
              </label>
              <select
                aria-label="条目类型"
                value={itemTypeFilter}
                onChange={(event) => setItemTypeFilter(event.target.value as ItemTypeFilter)}
                className="px-3 py-2.5 bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-[var(--radius-md)] text-sm"
              >
                <option value="all">全部</option>
                <option value="doc_chunk">文档分块</option>
                <option value="experience">经验</option>
              </select>
            </div>
            <div>
              <Input
                label="标签过滤"
                value={tagFilter}
                onChange={(event) => setTagFilter(event.target.value)}
                placeholder="单个标签"
              />
            </div>
          </div>
        </CardBody>
      </Card>

      {/* 文档区 */}
      <section className="mb-8">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">文档</h2>
          <span className="text-xs text-[var(--color-text-tertiary)]">
            共 {documents.length} 个
          </span>
        </div>

        {documentsQuery.isLoading ? (
          <Card className="py-8 text-center text-sm text-[var(--color-text-secondary)]">
            加载文档列表中…
          </Card>
        ) : documentsQuery.isError ? (
          <Card className="py-8 text-center text-sm text-[var(--color-error)]" role="alert">
            文档列表加载失败，请稍后重试。
          </Card>
        ) : documents.length === 0 ? (
          <Card className="py-8 text-center text-sm text-[var(--color-text-tertiary)]">
            还没有上传任何文档，可从上方拖拽或选择文件上传。
          </Card>
        ) : (
          <div className="space-y-2">
            {documents.map((document) => (
              <Card key={document.document_id}>
                <CardBody className="flex items-center justify-between gap-3 flex-wrap py-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-medium text-[var(--color-text-primary)] truncate max-w-xs">
                        {document.filename}
                      </span>
                      <Badge variant={documentStatusVariants[document.parse_status]}>
                        {documentStatusLabels[document.parse_status] ?? document.parse_status}
                      </Badge>
                    </div>
                    <div className="text-xs text-[var(--color-text-tertiary)] mt-1">
                      {document.mime} · {Math.round(document.size_bytes / 1024)} KB ·{' '}
                      {formatDate(document.created_at)}
                      {document.parse_error ? ` · ${document.parse_error}` : ''}
                    </div>
                  </div>
                  <button
                    type="button"
                    title="删除文档"
                    data-testid={`delete-document-${document.document_id}`}
                    onClick={() => handleDeleteDocument(document)}
                    className="p-1.5 rounded-[var(--radius-sm)] text-[var(--color-error)] hover:bg-[var(--color-error-light)] transition-colors"
                  >
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                      />
                    </svg>
                  </button>
                </CardBody>
              </Card>
            ))}
          </div>
        )}
      </section>

      {/* 条目区 */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">
            {searchText ? '检索结果' : '知识条目'}
          </h2>
          <span className="text-xs text-[var(--color-text-tertiary)]">共 {items.length} 条</span>
        </div>

        {itemsQuery.isLoading ? (
          <Card className="py-8 text-center text-sm text-[var(--color-text-secondary)]">
            加载知识条目中…
          </Card>
        ) : itemsQuery.isError ? (
          <Card className="py-8 text-center text-sm text-[var(--color-error)]" role="alert">
            知识条目加载失败，请稍后重试。
          </Card>
        ) : items.length === 0 ? (
          <Card className="py-8 text-center text-sm text-[var(--color-text-tertiary)]">
            {searchText ? '未检索到匹配条目，试试更换关键词或标签。' : '暂无知识条目，上传文档解析完成后将自动分块入库。'}
          </Card>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {items.map((item) => (
              <KnowledgeItemCard
                key={item.item_id}
                item={item}
                score={scores[item.item_id]}
                onOpen={(target) => {
                  setSelectedItem(target);
                  setDetailOpen(true);
                }}
                onDelete={handleDeleteItem}
              />
            ))}
          </div>
        )}
      </section>

      <KnowledgeDetailDrawer
        isOpen={detailOpen}
        onClose={() => setDetailOpen(false)}
        item={selectedItem ? { ...selectedItem, score: scores[selectedItem.item_id] } : null}
        document={documentQuery.data ?? null}
        isDocumentLoading={documentQuery.isLoading}
        onDelete={handleDeleteItem}
      />

      {itemsQuery.isError && (
        <div className="mt-4 text-center">
          <Button variant="secondary" size="sm" onClick={() => itemsQuery.refetch()}>
            重试加载条目
          </Button>
        </div>
      )}
    </div>
  );
}
