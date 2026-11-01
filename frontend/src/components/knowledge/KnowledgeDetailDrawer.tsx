import { Badge, Button, Drawer } from '../ui';
import { formatDate, getImportanceLabel } from '../../lib/utils';
import type { KnowledgeDocument, KnowledgeItem } from '../../api/knowledge';

/** 文档详情（含文本预览与分块数，来自 GET /knowledge/documents/{id}） */
export type KnowledgeDocumentDetail = KnowledgeDocument & {
  text_preview?: string | null;
  chunk_count?: number;
};

export interface KnowledgeDetailDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  /** 当前选中的知识条目；命中分数通过 score 字段可选展示 */
  item: (KnowledgeItem & { score?: number }) | null;
  /** 条目所属文档（当 item.document_id 存在时由页面拉取） */
  document?: KnowledgeDocumentDetail | null;
  isDocumentLoading?: boolean;
  onDelete?: (item: KnowledgeItem) => void;
}

const itemTypeLabels: Record<KnowledgeItem['item_type'], string> = {
  doc_chunk: '文档分块',
  experience: '经验',
};

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

/**
 * 条目详情抽屉：内容、标签、重要性、类型、所属文档、命中分数；
 * 文档条目额外展示解析状态与文本预览。
 */
export function KnowledgeDetailDrawer({
  isOpen,
  onClose,
  item,
  document,
  isDocumentLoading,
  onDelete,
}: KnowledgeDetailDrawerProps) {
  return (
    <Drawer isOpen={isOpen} onClose={onClose} title="知识条目详情" width="520px">
      {!item ? (
        <p className="text-sm text-[var(--color-text-tertiary)]">未选择条目</p>
      ) : (
        <div className="space-y-4">
          <div>
            <h3 className="text-sm font-medium text-[var(--color-text-secondary)] mb-2">标题</h3>
            <p className="text-[var(--color-text-primary)] break-words">
              {item.title || '（无标题）'}
            </p>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <h3 className="text-sm font-medium text-[var(--color-text-secondary)] mb-2">类型</h3>
              <Badge variant={item.item_type === 'experience' ? 'primary' : 'secondary'}>
                {itemTypeLabels[item.item_type] ?? item.item_type}
              </Badge>
            </div>
            <div>
              <h3 className="text-sm font-medium text-[var(--color-text-secondary)] mb-2">重要性</h3>
              <span className="text-[var(--color-text-primary)]">
                {getImportanceLabel(item.importance)}（{item.importance}/5）
              </span>
            </div>
          </div>

          {typeof item.score === 'number' && (
            <div>
              <h3 className="text-sm font-medium text-[var(--color-text-secondary)] mb-2">
                命中分数
              </h3>
              <span className="text-[var(--color-text-primary)]">{item.score.toFixed(4)}</span>
            </div>
          )}

          <div>
            <h3 className="text-sm font-medium text-[var(--color-text-secondary)] mb-2">标签</h3>
            <div className="flex gap-2 flex-wrap">
              {item.tags.length > 0 ? (
                item.tags.map((tag) => (
                  <Badge key={tag} variant="primary">
                    {tag}
                  </Badge>
                ))
              ) : (
                <span className="text-[var(--color-text-tertiary)]">无标签</span>
              )}
            </div>
          </div>

          <div>
            <h3 className="text-sm font-medium text-[var(--color-text-secondary)] mb-2">内容</h3>
            <p className="text-[var(--color-text-primary)] whitespace-pre-wrap break-words">
              {item.content}
            </p>
          </div>

          <div>
            <h3 className="text-sm font-medium text-[var(--color-text-secondary)] mb-2">所属文档</h3>
            {item.document_id ? (
              <div className="space-y-2">
                {isDocumentLoading ? (
                  <p className="text-sm text-[var(--color-text-tertiary)]">加载文档信息…</p>
                ) : document ? (
                  <>
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm text-[var(--color-text-primary)] break-all">
                        {document.filename}
                      </span>
                      <Badge variant={documentStatusVariants[document.parse_status]}>
                        {documentStatusLabels[document.parse_status] ?? document.parse_status}
                      </Badge>
                      {typeof document.chunk_count === 'number' && (
                        <span className="text-xs text-[var(--color-text-tertiary)]">
                          {document.chunk_count} 个分块
                        </span>
                      )}
                    </div>
                    {document.parse_error && (
                      <p className="text-xs text-[var(--color-error)]">
                        解析错误：{document.parse_error}
                      </p>
                    )}
                    <div>
                      <h4 className="text-xs font-medium text-[var(--color-text-secondary)] mb-1">
                        文本预览
                      </h4>
                      <p className="text-sm text-[var(--color-text-secondary)] whitespace-pre-wrap break-words max-h-56 overflow-y-auto">
                        {document.text_preview || '（暂无预览文本）'}
                      </p>
                    </div>
                  </>
                ) : (
                  <p className="text-sm text-[var(--color-text-tertiary)]">文档信息不可用</p>
                )}
                <p className="text-xs text-[var(--color-text-tertiary)] break-all">
                  document_id：{item.document_id}
                </p>
              </div>
            ) : (
              <span className="text-sm text-[var(--color-text-tertiary)]">独立经验条目</span>
            )}
          </div>

          <div>
            <h3 className="text-sm font-medium text-[var(--color-text-secondary)] mb-2">创建时间</h3>
            <span className="text-[var(--color-text-primary)]">{formatDate(item.created_at)}</span>
          </div>

          {onDelete && (
            <div className="flex gap-2 pt-4 border-t border-[var(--color-border)]">
              <Button variant="danger" onClick={() => onDelete(item)}>
                删除条目
              </Button>
              <Button variant="secondary" onClick={onClose}>
                关闭
              </Button>
            </div>
          )}
        </div>
      )}
    </Drawer>
  );
}
