import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Search,
  Plus,
  Filter,
  Trash2,
  Archive,
  Edit3,
  Tag,
  Star,
  Brain,
  CheckSquare,
  Square,
  X,
  Loader2,
  Tags
} from 'lucide-react'
import { api } from '../api/client'
import { formatDate, truncateText, getImportanceColor, getImportanceLabel } from '../lib/utils'
import { cn } from '../lib/utils'

interface Memory {
  id: number
  content: string
  type: string
  importance: number
  tags: string[]
  created_at: string
  is_archived: boolean
  emotion_score?: number
}

export function MemoriesPage() {
  const queryClient = useQueryClient()
  const [searchQuery, setSearchQuery] = useState<string>('')
  const [filterType, setFilterType] = useState<'all' | 'long_term' | 'short_term' | 'permanent'>('all')
  const [showAddModal, setShowAddModal] = useState(false)
  const [showEditModal, setShowEditModal] = useState(false)
  const [editingMemory, setEditingMemory] = useState<Memory | null>(null)
  const [newMemory, setNewMemory] = useState({
    content: '',
    type: 'long_term',
    importance: 3,
    tags: ''
  })

  // Batch operation states
  const [selectedMemories, setSelectedMemories] = useState<Set<number>>(new Set())
  const [isBatchMode, setIsBatchMode] = useState(false)
  const [showBatchTagModal, setShowBatchTagModal] = useState(false)
  const [batchTags, setBatchTags] = useState('')
  const [batchTagOperation, setBatchTagOperation] = useState<'add' | 'remove' | 'set'>('add')

  const { data: memories, isLoading, refetch } = useQuery({
    queryKey: ['memories', filterType],
    queryFn: () => api.getMemories({ type: filterType === 'all' ? undefined : filterType }),
    refetchInterval: 5000
  })

  const handleCreateMemory = async () => {
    try {
      await api.createMemory({
        content: newMemory.content,
        type: newMemory.type,
        importance: newMemory.importance,
        tags: newMemory.tags.split(',').map(t => t.trim()).filter(Boolean)
      })
      setShowAddModal(false)
      setNewMemory({ content: '', type: 'long_term', importance: 3, tags: '' })
      refetch()
    } catch (error) {
      console.error('创建记忆失败:', error)
    }
  }

  const handleDeleteMemory = async (id: number) => {
    if (!confirm('确定要删除这条记忆吗？')) return
    try {
      await api.deleteMemory(id)
      refetch()
    } catch (error) {
      console.error('删除记忆失败:', error)
    }
  }

  const handleArchiveMemory = async (id: number) => {
    try {
      await api.archiveMemory(id)
      refetch()
    } catch (error) {
      console.error('归档记忆失败:', error)
    }
  }

  const handleEditMemory = (memory: Memory) => {
    setEditingMemory(memory)
    setShowEditModal(true)
  }

  const handleUpdateMemory = async () => {
    if (!editingMemory) return
    try {
      await api.updateMemory(editingMemory.id, {
        content: editingMemory.content,
        tags: editingMemory.tags,
        importance: editingMemory.importance
      })
      setShowEditModal(false)
      setEditingMemory(null)
      refetch()
    } catch (error) {
      console.error('更新记忆失败:', error)
    }
  }

  // Batch operations
  const toggleMemorySelection = (id: number) => {
    const newSelected = new Set(selectedMemories)
    if (newSelected.has(id)) {
      newSelected.delete(id)
    } else {
      newSelected.add(id)
    }
    setSelectedMemories(newSelected)
  }

  const selectAllMemories = () => {
    if (selectedMemories.size === filteredMemories.length) {
      setSelectedMemories(new Set())
    } else {
      setSelectedMemories(new Set(filteredMemories.map((m: Memory) => m.id)))
    }
  }

  const clearSelection = () => {
    setSelectedMemories(new Set())
    setIsBatchMode(false)
  }

  // Batch mutations
  const batchDeleteMutation = useMutation({
    mutationFn: (ids: number[]) => api.batchDeleteMemories(ids),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['memories'] })
      clearSelection()
    },
    onError: (error: any) => {
      console.error('批量删除失败:', error)
      alert(`批量删除失败: ${error?.response?.data?.detail || error?.message || '未知错误'}`)
    }
  })

  const batchArchiveMutation = useMutation({
    mutationFn: (ids: number[]) => api.batchArchiveMemories(ids),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['memories'] })
      clearSelection()
    },
    onError: (error: any) => {
      console.error('批量归档失败:', error)
      alert(`批量归档失败: ${error?.response?.data?.detail || error?.message || '未知错误'}`)
    }
  })

  const batchUpdateTagsMutation = useMutation({
    mutationFn: ({ ids, tags, operation }: { ids: number[]; tags: string[]; operation: 'add' | 'remove' | 'set' }) =>
      api.batchUpdateTags(ids, tags, operation),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['memories'] })
      setShowBatchTagModal(false)
      setBatchTags('')
      clearSelection()
    },
    onError: (error: any) => {
      console.error('批量更新标签失败:', error)
      alert(`批量更新标签失败: ${error?.response?.data?.detail || error?.message || '未知错误'}`)
    }
  })

  const handleBatchDelete = () => {
    if (selectedMemories.size === 0) return
    if (!confirm(`确定要删除选中的 ${selectedMemories.size} 条记忆吗？`)) return
    batchDeleteMutation.mutate(Array.from(selectedMemories))
  }

  const handleBatchArchive = () => {
    if (selectedMemories.size === 0) return
    batchArchiveMutation.mutate(Array.from(selectedMemories))
  }

  const handleBatchUpdateTags = () => {
    if (selectedMemories.size === 0) return
    const tags = batchTags.split(',').map(t => t.trim()).filter(Boolean)
    if (tags.length === 0) return
    batchUpdateTagsMutation.mutate({
      ids: Array.from(selectedMemories),
      tags,
      operation: batchTagOperation
    })
  }

  const filteredMemories = memories?.memories?.filter((memory: Memory) => {
    if (!searchQuery) return true
    return memory.content.toLowerCase().includes(searchQuery.toLowerCase()) ||
           (memory.tags && memory.tags.some(tag => tag.toLowerCase().includes(searchQuery.toLowerCase())))
  }) || []

  return (
    <div className="h-full flex flex-col">
      {/* Toolbar */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <input
              type="text"
              placeholder="搜索记忆..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9 pr-4 py-2 bg-muted rounded-lg text-sm w-64 focus:outline-none focus:ring-2 focus:ring-primary/50"
            />
          </div>

          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-muted-foreground" />
            <select
              value={filterType}
              onChange={(e) => setFilterType(e.target.value as 'all' | 'long_term' | 'short_term' | 'permanent')}
              className="bg-muted rounded-lg px-3 py-2 text-sm focus:outline-none"
            >
              <option value="all">全部类型</option>
              <option value="permanent">永久记忆</option>
              <option value="long_term">长期记忆</option>
              <option value="short_term">短期记忆</option>
            </select>
          </div>

          {/* Batch Mode Toggle */}
          <button
            onClick={() => {
              setIsBatchMode(!isBatchMode)
              if (isBatchMode) clearSelection()
            }}
            className={cn(
              "flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors",
              isBatchMode
                ? "bg-primary text-primary-foreground"
                : "bg-muted text-muted-foreground hover:bg-accent"
            )}
          >
            <CheckSquare className="w-4 h-4" />
            {isBatchMode ? '退出批量' : '批量操作'}
          </button>
        </div>

        <button
          onClick={() => setShowAddModal(true)}
          className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors"
        >
          <Plus className="w-4 h-4" />
          新建记忆
        </button>
      </div>

      {/* Batch Operations Toolbar */}
      {isBatchMode && (
        <div className="flex items-center justify-between mb-4 p-3 bg-primary/5 border border-primary/20 rounded-lg">
          <div className="flex items-center gap-4">
            <button
              onClick={selectAllMemories}
              className="flex items-center gap-2 text-sm font-medium"
            >
              {selectedMemories.size === filteredMemories.length ? (
                <CheckSquare className="w-4 h-4" />
              ) : (
                <Square className="w-4 h-4" />
              )}
              全选 ({selectedMemories.size}/{filteredMemories.length})
            </button>
            {selectedMemories.size > 0 && (
              <span className="text-sm text-muted-foreground">
                已选择 {selectedMemories.size} 条记忆
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {selectedMemories.size > 0 && (
              <>
                <button
                  onClick={() => setShowBatchTagModal(true)}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-muted rounded-lg hover:bg-accent transition-colors"
                >
                  <Tags className="w-4 h-4" />
                  标签
                </button>
                <button
                  onClick={handleBatchArchive}
                  disabled={batchArchiveMutation.isPending}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-muted rounded-lg hover:bg-accent transition-colors disabled:opacity-50"
                >
                  {batchArchiveMutation.isPending ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Archive className="w-4 h-4" />
                  )}
                  归档
                </button>
                <button
                  onClick={handleBatchDelete}
                  disabled={batchDeleteMutation.isPending}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-destructive/10 text-destructive rounded-lg hover:bg-destructive/20 transition-colors disabled:opacity-50"
                >
                  {batchDeleteMutation.isPending ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Trash2 className="w-4 h-4" />
                  )}
                  删除
                </button>
              </>
            )}
            <button
              onClick={clearSelection}
              className="p-1.5 hover:bg-muted rounded-lg transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {/* Memories Grid */}
      {isLoading ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="animate-spin w-8 h-8 border-2 border-primary border-t-transparent rounded-full" />
        </div>
      ) : filteredMemories.length === 0 ? (
        <div className="flex-1 flex flex-col items-center justify-center text-center">
          <Brain className="w-16 h-16 text-muted-foreground/50 mb-4" />
          <h3 className="text-lg font-medium text-muted-foreground">暂无记忆</h3>
          <p className="text-sm text-muted-foreground/70 mt-1">
            点击"新建记忆"按钮添加您的第一条记忆
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {filteredMemories.map((memory: Memory) => (
            <div
              key={memory.id}
              className={cn(
                "bg-card border border-border rounded-xl p-4 hover:shadow-md transition-all",
                memory.is_archived && "opacity-60",
                isBatchMode && selectedMemories.has(memory.id) && "ring-2 ring-primary border-primary"
              )}
              onClick={() => isBatchMode && toggleMemorySelection(memory.id)}
            >
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-2">
                  {isBatchMode ? (
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        toggleMemorySelection(memory.id)
                      }}
                      className="p-1 hover:bg-muted rounded transition-colors"
                    >
                      {selectedMemories.has(memory.id) ? (
                        <CheckSquare className="w-4 h-4 text-primary" />
                      ) : (
                        <Square className="w-4 h-4 text-muted-foreground" />
                      )}
                    </button>
                  ) : (
                    <span className={cn(
                      "w-2 h-2 rounded-full",
                      getImportanceColor(memory.importance)
                    )} />
                  )}
                  <span className="text-xs text-muted-foreground">
                    {getImportanceLabel(memory.importance)}
                  </span>
                  {memory.is_archived && (
                    <span className="text-xs px-2 py-0.5 bg-muted rounded-full">
                      已归档
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-1">
                  {!isBatchMode && (
                    <>
                      <button
                        onClick={() => handleArchiveMemory(memory.id)}
                        className="p-1.5 hover:bg-muted rounded-lg transition-colors"
                        title="归档"
                      >
                        <Archive className="w-4 h-4 text-muted-foreground" />
                      </button>
                      <button
                        onClick={() => handleEditMemory(memory)}
                        className="p-1.5 hover:bg-muted rounded-lg transition-colors"
                        title="编辑"
                      >
                        <Edit3 className="w-4 h-4 text-muted-foreground" />
                      </button>
                      <button
                        onClick={() => handleDeleteMemory(memory.id)}
                        className="p-1.5 hover:bg-destructive/10 hover:text-destructive rounded-lg transition-colors"
                        title="删除"
                      >
                        <Trash2 className="w-4 h-4 text-muted-foreground" />
                      </button>
                    </>
                  )}
                </div>
              </div>

              <p className="text-sm mb-3 line-clamp-4">
                {truncateText(memory.content, 200)}
              </p>

              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 flex-wrap">
                  {memory.tags?.map((tag) => (
                    <span
                      key={tag}
                      className="text-xs px-2 py-0.5 bg-primary/10 text-primary rounded-full"
                    >
                      {tag}
                    </span>
                  ))}
                  {(!memory.tags || memory.tags.length === 0) && (
                    <span className="text-xs text-muted-foreground">无标签</span>
                  )}
                </div>
                <span className="text-xs text-muted-foreground">
                  {formatDate(memory.created_at)}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add Memory Modal */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-card rounded-xl p-6 w-full max-w-lg mx-4">
            <h3 className="text-lg font-semibold mb-4">新建记忆</h3>
            
            <div className="space-y-4">
              <div>
                <label className="text-sm font-medium mb-1.5 block">内容</label>
                <textarea
                  value={newMemory.content}
                  onChange={(e) => setNewMemory({ ...newMemory, content: e.target.value })}
                  placeholder="输入记忆内容..."
                  className="w-full px-3 py-2 bg-muted rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50 min-h-[100px]"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-sm font-medium mb-1.5 block">类型</label>
                  <select
                    value={newMemory.type}
                    onChange={(e) => setNewMemory({ ...newMemory, type: e.target.value })}
                    className="w-full px-3 py-2 bg-muted rounded-lg focus:outline-none"
                  >
                    <option value="long_term">长期记忆</option>
                    <option value="short_term">短期记忆</option>
                    <option value="permanent">永久记忆</option>
                  </select>
                </div>

                <div>
                  <label className="text-sm font-medium mb-1.5 block">重要性</label>
                  <div className="flex items-center gap-1">
                    {[1, 2, 3, 4, 5].map((star) => (
                      <button
                        key={star}
                        onClick={() => setNewMemory({ ...newMemory, importance: star })}
                        className="p-1"
                      >
                        <Star
                          className={cn(
                            "w-5 h-5",
                            star <= newMemory.importance
                              ? "fill-yellow-400 text-yellow-400"
                              : "text-muted-foreground"
                          )}
                        />
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <div>
                <label className="text-sm font-medium mb-1.5 block">标签（用逗号分隔）</label>
                <div className="relative">
                  <Tag className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <input
                    type="text"
                    value={newMemory.tags}
                    onChange={(e) => setNewMemory({ ...newMemory, tags: e.target.value })}
                    placeholder="标签1, 标签2, 标签3"
                    className="w-full pl-9 pr-3 py-2 bg-muted rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
                  />
                </div>
              </div>
            </div>

            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => setShowAddModal(false)}
                className="px-4 py-2 text-muted-foreground hover:bg-muted rounded-lg transition-colors"
              >
                取消
              </button>
              <button
                onClick={handleCreateMemory}
                disabled={!newMemory.content.trim()}
                className="px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors"
              >
                创建
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit Memory Modal */}
      {showEditModal && editingMemory && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-card rounded-xl p-6 w-full max-w-lg mx-4">
            <h3 className="text-lg font-semibold mb-4">编辑记忆</h3>
            
            <div className="space-y-4">
              <div>
                <label className="text-sm font-medium mb-1.5 block">内容</label>
                <textarea
                  value={editingMemory.content}
                  onChange={(e) => setEditingMemory({ ...editingMemory, content: e.target.value })}
                  placeholder="输入记忆内容..."
                  className="w-full px-3 py-2 bg-muted rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50 min-h-[100px]"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-sm font-medium mb-1.5 block">类型</label>
                  <select
                    value={editingMemory.type}
                    onChange={(e) => setEditingMemory({ ...editingMemory, type: e.target.value })}
                    className="w-full px-3 py-2 bg-muted rounded-lg focus:outline-none"
                  >
                    <option value="long_term">长期记忆</option>
                    <option value="short_term">短期记忆</option>
                    <option value="permanent">永久记忆</option>
                  </select>
                </div>

                <div>
                  <label className="text-sm font-medium mb-1.5 block">重要性</label>
                  <div className="flex items-center gap-1">
                    {[1, 2, 3, 4, 5].map((star) => (
                      <button
                        key={star}
                        onClick={() => setEditingMemory({ ...editingMemory, importance: star })}
                        className="p-1"
                      >
                        <Star
                          className={cn(
                            "w-5 h-5",
                            star <= editingMemory.importance
                              ? "fill-yellow-400 text-yellow-400"
                              : "text-muted-foreground"
                          )}
                        />
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <div>
                <label className="text-sm font-medium mb-1.5 block">标签（用逗号分隔）</label>
                <div className="relative">
                  <Tag className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <input
                    type="text"
                    value={editingMemory.tags.join(', ')}
                    onChange={(e) => setEditingMemory({ ...editingMemory, tags: e.target.value.split(',').map(t => t.trim()).filter(Boolean) })}
                    placeholder="标签1, 标签2, 标签3"
                    className="w-full pl-9 pr-3 py-2 bg-muted rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
                  />
                </div>
              </div>
            </div>

            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => {
                  setShowEditModal(false)
                  setEditingMemory(null)
                }}
                className="px-4 py-2 text-muted-foreground hover:bg-muted rounded-lg transition-colors"
              >
                取消
              </button>
              <button
                onClick={handleUpdateMemory}
                disabled={!editingMemory.content.trim()}
                className="px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors"
              >
                保存
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Batch Tag Modal */}
      {showBatchTagModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-card rounded-xl p-6 w-full max-w-md mx-4">
            <h3 className="text-lg font-semibold mb-4">
              批量更新标签 ({selectedMemories.size} 条记忆)
            </h3>

            <div className="space-y-4">
              <div>
                <label className="text-sm font-medium mb-1.5 block">操作类型</label>
                <div className="flex gap-2">
                  {(['add', 'remove', 'set'] as const).map((op) => (
                    <button
                      key={op}
                      onClick={() => setBatchTagOperation(op)}
                      className={cn(
                        "flex-1 px-3 py-2 text-sm rounded-lg transition-colors",
                        batchTagOperation === op
                          ? "bg-primary text-primary-foreground"
                          : "bg-muted hover:bg-accent"
                      )}
                    >
                      {op === 'add' ? '添加' : op === 'remove' ? '移除' : '设置'}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="text-sm font-medium mb-1.5 block">
                  标签（用逗号分隔）
                </label>
                <div className="relative">
                  <Tag className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <input
                    type="text"
                    value={batchTags}
                    onChange={(e) => setBatchTags(e.target.value)}
                    placeholder="标签1, 标签2, 标签3"
                    className="w-full pl-9 pr-3 py-2 bg-muted rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
                  />
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  {batchTagOperation === 'add' && '将标签添加到选中的记忆'}
                  {batchTagOperation === 'remove' && '从选中的记忆中移除标签'}
                  {batchTagOperation === 'set' && '替换选中记忆的所有标签'}
                </p>
              </div>
            </div>

            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => {
                  setShowBatchTagModal(false)
                  setBatchTags('')
                }}
                className="px-4 py-2 text-muted-foreground hover:bg-muted rounded-lg transition-colors"
              >
                取消
              </button>
              <button
                onClick={handleBatchUpdateTags}
                disabled={!batchTags.trim() || batchUpdateTagsMutation.isPending}
                className="px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors flex items-center gap-2"
              >
                {batchUpdateTagsMutation.isPending && (
                  <Loader2 className="w-4 h-4 animate-spin" />
                )}
                确认
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
