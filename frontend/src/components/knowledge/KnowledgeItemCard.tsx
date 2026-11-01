import { Badge, Card, CardBody } from '../ui';
import { formatDate, getImportanceLabel, truncate } from '../../lib/utils';
import type { KnowledgeItem } from '../../api/knowledge';

export interface KnowledgeItemCardProps {
  item: KnowledgeItem;
  /** 检索命中分数；仅在搜索结果中出现 */
  score?: number;
  onOpen?: (item: KnowledgeItem) => void;
  onDelete?: (item: KnowledgeItem) => void;
}

const itemTypeLabels: Record<KnowledgeItem['item_type'], string> = {
  doc_chunk: '文档分块',
  experience: '经验',
};

/**
 * 知识条目卡片：展示类型/标题/标签/重要性/内容摘要，支持打开详情与删除。
 */
export function KnowledgeItemCard({ item, score, onOpen, onDelete }: KnowledgeItemCardProps) {
  const displayTitle = item.title || truncate(item.content, 40);

  return (
    <Card
      hoverable={Boolean(onOpen)}
      className="h-full"
      onClick={() => onOpen?.(item)}
      data-testid={`knowledge-item-${item.item_id}`}
    >
      <CardBody>
        <div className="flex items-start justify-between gap-2 mb-2">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant={item.item_type === 'experience' ? 'primary' : 'secondary'} size="sm">
              {itemTypeLabels[item.item_type] ?? item.item_type}
            </Badge>
            {typeof score === 'number' && (
              <span className="text-xs text-[var(--color-text-tertiary)]">
                匹配度 {score.toFixed(3)}
              </span>
            )}
          </div>
          {onDelete && (
            <button
              type="button"
              title="删除条目"
              data-testid={`delete-item-${item.item_id}`}
              onClick={(event) => {
                event.stopPropagation();
                onDelete(item);
              }}
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
          )}
        </div>

        <h3 className="text-sm font-semibold text-[var(--color-text-primary)] mb-1.5 line-clamp-2">
          {displayTitle}
        </h3>
        <p className="text-sm text-[var(--color-text-secondary)] line-clamp-3 mb-3">
          {truncate(item.content, 160)}
        </p>

        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-1 flex-wrap">
            {item.tags.slice(0, 3).map((tag) => (
              <Badge key={tag} variant="primary" size="sm">
                {tag}
              </Badge>
            ))}
            {item.tags.length > 3 && (
              <span className="text-xs text-[var(--color-text-tertiary)]">
                +{item.tags.length - 3}
              </span>
            )}
          </div>
          <span className="text-xs text-[var(--color-text-tertiary)]">
            {getImportanceLabel(item.importance)} · {formatDate(item.created_at)}
          </span>
        </div>
      </CardBody>
    </Card>
  );
}
