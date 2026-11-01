import { useRef, useState } from 'react';
import { Button, Card, CardBody, Input } from '../ui';
import { knowledgeApi } from '../../api/knowledge';

export interface KnowledgeUploadPanelProps {
  /** 当前知识库所属 agent；上传时写入 multipart 的 agent_id 字段 */
  agentId: string;
  /** 上传成功后回调，由页面统一 invalidate 文档列表 */
  onUploaded?: () => void;
}

/**
 * 将 axios/网络异常转成用户可理解的中文文案。
 * 413 → 文件大小超限；415 → 类型不在白名单；503 → 知识库未启用或不可用。
 */
function resolveUploadError(error: unknown): string {
  const status = (error as { response?: { status?: number } })?.response?.status;
  if (status === 413) {
    return '文件超出大小限制（文档默认 20MB、媒体默认 200MB），请压缩或拆分后重试。';
  }
  if (status === 415) {
    return '不支持的文件类型，请上传 PDF/DOCX/TXT/MD、图片、音频或视频。';
  }
  if (status === 503) {
    return '知识库当前未启用或服务不可用，请稍后重试。';
  }
  return '上传失败，请检查网络或后端服务后重试。';
}

/**
 * 知识库上传面板：支持拖拽与文件选择、标签输入、上传进度、413/415 错误提示。
 */
export function KnowledgeUploadPanel({ agentId, onUploaded }: KnowledgeUploadPanelProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [tagsInput, setTagsInput] = useState('');
  const [title, setTitle] = useState('');
  const [progress, setProgress] = useState(0);
  const [isUploading, setIsUploading] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const pickFiles = (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setPendingFiles(Array.from(files));
    setError(null);
    setNotice(null);
    setProgress(0);
  };

  const handleUpload = async () => {
    if (pendingFiles.length === 0 || isUploading) return;
    setIsUploading(true);
    setError(null);
    setNotice(null);
    setProgress(0);

    const tags = tagsInput
      .split(',')
      .map((tag) => tag.trim())
      .filter(Boolean);

    let deduplicatedCount = 0;
    try {
      for (const file of pendingFiles) {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('agent_id', agentId);
        formData.append('tags', JSON.stringify(tags));
        if (title.trim()) {
          formData.append('title', title.trim());
        }
        const result = await knowledgeApi.uploadDocument(formData, (percent) =>
          setProgress(percent)
        );
        if (result.deduplicated) {
          deduplicatedCount += 1;
        }
      }

      const dedupNote =
        deduplicatedCount > 0 ? `，其中 ${deduplicatedCount} 个与已有文档重复已复用` : '';
      setNotice(`已上传 ${pendingFiles.length} 个文件${dedupNote}，正在后台解析。`);
      setPendingFiles([]);
      setTitle('');
      setProgress(0);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
      onUploaded?.();
    } catch (uploadError) {
      setError(resolveUploadError(uploadError));
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <Card className="mb-6">
      <CardBody>
        <div
          onDragOver={(event) => {
            event.preventDefault();
            setIsDragOver(true);
          }}
          onDragLeave={() => setIsDragOver(false)}
          onDrop={(event) => {
            event.preventDefault();
            setIsDragOver(false);
            pickFiles(event.dataTransfer.files);
          }}
          className={`border-2 border-dashed rounded-[var(--radius-md)] px-4 py-6 text-center transition-colors ${
            isDragOver
              ? 'border-[var(--color-accent)] bg-[var(--color-accent-light)]'
              : 'border-[var(--color-border)]'
          }`}
        >
          <p className="text-sm text-[var(--color-text-secondary)] mb-2">
            拖拽文件到此处，或点击下方按钮选择文件
          </p>
          <p className="text-xs text-[var(--color-text-tertiary)] mb-3">
            支持 PDF / DOCX / TXT / MD、图片（PNG/JPG/WEBP/BMP）、音频与视频
          </p>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            data-testid="knowledge-file-input"
            className="hidden"
            onChange={(event) => pickFiles(event.target.files)}
          />
          <Button
            variant="secondary"
            size="sm"
            onClick={() => fileInputRef.current?.click()}
            disabled={isUploading}
          >
            选择文件
          </Button>
          {pendingFiles.length > 0 && (
            <div className="mt-3 text-xs text-[var(--color-text-secondary)]">
              已选择 {pendingFiles.length} 个文件：{pendingFiles.map((file) => file.name).join('、')}
            </div>
          )}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
          <Input
            label="标签（逗号分隔，可选）"
            value={tagsInput}
            onChange={(event) => setTagsInput(event.target.value)}
            placeholder="例如：项目资料, 会议纪要"
            disabled={isUploading}
          />
          <Input
            label="文档标题（可选）"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="不填则使用文件名"
            disabled={isUploading}
          />
        </div>

        {isUploading && (
          <div className="mt-4">
            <div className="flex items-center justify-between text-xs text-[var(--color-text-secondary)] mb-1">
              <span>上传中…</span>
              <span>{progress}%</span>
            </div>
            <div className="w-full h-1.5 rounded-full bg-[var(--color-bg-tertiary)] overflow-hidden">
              <div
                className="h-full bg-[var(--color-accent)] transition-all"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        )}

        {error && (
          <p role="alert" className="mt-3 text-sm text-[var(--color-error)]">
            {error}
          </p>
        )}
        {notice && (
          <p className="mt-3 text-sm text-[var(--color-success)]">{notice}</p>
        )}

        <div className="flex justify-end gap-2 mt-4">
          <Button
            onClick={handleUpload}
            loading={isUploading}
            disabled={pendingFiles.length === 0 || isUploading}
          >
            开始上传
          </Button>
        </div>
      </CardBody>
    </Card>
  );
}
