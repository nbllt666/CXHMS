// ========== 共享类型：Memory ==========
// F8: 统一 Memory 类型定义。
// 唯一权威来源；pages/MemoriesPage.tsx re-export 此处定义。

/**
 * 记忆条目。与后端 /api/memories 返回结构对齐。
 */
export interface Memory {
  id: number;
  content: string;
  type: string;
  importance: number;
  tags: string[];
  created_at: string;
  is_archived: boolean;
  emotion_score?: number;
}
