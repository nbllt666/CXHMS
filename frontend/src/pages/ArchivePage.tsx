import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import {
  Archive,
  Merge,
  Search,
  Settings,
  BarChart3,
  Layers,
  AlertCircle,
  CheckCircle2,
} from 'lucide-react';
import { api } from '../api';
import { cn } from '../lib/utils';

interface ArchiveStats {
  archive_level_counts: Record<number, number>;
  total_archived: number;
  merge_count: number;
  duplicate_count: number;
}

interface DuplicateGroup {
  group_id: string;
  memory_ids: number[];
  canonical_id: number;
  similarity_matrix: Record<string, number>;
}

export function ArchivePage() {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<'overview' | 'duplicates' | 'settings'>('overview');
  const [isProcessing, setIsProcessing] = useState(false);
  const [processResult, setProcessResult] = useState<string | null>(null);
  const [similarityThreshold, setSimilarityThreshold] = useState(0.85);
  const [autoArchiveDays, setAutoArchiveDays] = useState(30);

  const { data: stats, refetch: refetchStats } = useQuery<ArchiveStats>({
    queryKey: ['archiveStats'],
    queryFn: () => api.getArchiveStats(),
    refetchInterval: 10000,
  });

  const { data: duplicates, refetch: refetchDuplicates } = useQuery<{
    duplicate_groups: DuplicateGroup[];
  }>({
    queryKey: ['duplicates'],
    queryFn: () => api.detectDuplicates(),
    enabled: activeTab === 'duplicates',
  });

  const handleAutoArchive = async () => {
    setIsProcessing(true);
    setProcessResult(null);
    try {
      const result = await api.autoArchiveProcess();
      setProcessResult(
        t('archive.archiveComplete', {
          archived: result.results?.archived?.length ?? 0,
          merged: result.results?.merged?.length ?? 0,
        })
      );
      refetchStats();
    } catch {
      setProcessResult(t('archive.archiveFailed'));
    } finally {
      setIsProcessing(false);
    }
  };

  const handleDetectDuplicates = async () => {
    setIsProcessing(true);
    try {
      await refetchDuplicates();
    } finally {
      setIsProcessing(false);
    }
  };

  const handleMergeGroup = async (group: DuplicateGroup) => {
    if (!confirm(t('archive.confirmMerge', { count: group.memory_ids.length }))) return;

    setIsProcessing(true);
    try {
      await api.mergeMemories(group.memory_ids);
      refetchDuplicates();
      refetchStats();
    } catch (error) {
      console.error('合并失败:', error);
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div className="h-full flex flex-col">
      {/* Tabs */}
      <div className="flex items-center gap-1 mb-6 border-b border-border">
        {[
          { id: 'overview', label: t('archive.overview'), icon: BarChart3 },
          { id: 'duplicates', label: t('archive.duplicatesManagement'), icon: Search },
          { id: 'settings', label: t('common.settings'), icon: Settings },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as 'overview' | 'duplicates' | 'settings')}
            className={cn(
              'flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors',
              activeTab === tab.id
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            )}
          >
            <tab.icon className="w-4 h-4" />
            {tab.label}
          </button>
        ))}
      </div>

      {/* Overview Tab */}
      {activeTab === 'overview' && (
        <div className="space-y-6">
          {/* Stats Cards */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="bg-card border border-border rounded-xl p-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                  <Archive className="w-5 h-5 text-primary" />
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">{t('archive.totalArchivedLabel')}</p>
                  <p className="text-2xl font-semibold">{stats?.total_archived || 0}</p>
                </div>
              </div>
            </div>

            <div className="bg-card border border-border rounded-xl p-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-green-500/10 flex items-center justify-center">
                  <Merge className="w-5 h-5 text-green-500" />
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">{t('archive.mergeRecords')}</p>
                  <p className="text-2xl font-semibold">{stats?.merge_count || 0}</p>
                </div>
              </div>
            </div>

            <div className="bg-card border border-border rounded-xl p-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-yellow-500/10 flex items-center justify-center">
                  <AlertCircle className="w-5 h-5 text-yellow-500" />
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">{t('archive.duplicateDetection')}</p>
                  <p className="text-2xl font-semibold">{stats?.duplicate_count || 0}</p>
                </div>
              </div>
            </div>

            <div className="bg-card border border-border rounded-xl p-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-blue-500/10 flex items-center justify-center">
                  <Layers className="w-5 h-5 text-blue-500" />
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">{t('archive.archiveLevels')}</p>
                  <p className="text-2xl font-semibold">
                    {Object.keys(stats?.archive_level_counts || {}).length}
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Archive Levels */}
          <div className="bg-card border border-border rounded-xl p-6">
            <h3 className="font-semibold mb-4">{t('archive.archiveLevelDistribution')}</h3>
            <div className="space-y-3">
              {stats?.archive_level_counts &&
                Object.entries(stats.archive_level_counts).map(([level, count]) => (
                  <div key={level} className="flex items-center gap-4">
                    <span className="w-16 text-sm font-medium">
                      {t('archive.level')} {level}
                    </span>
                    <div className="flex-1 h-6 bg-muted rounded-full overflow-hidden">
                      <div
                        className="h-full bg-primary rounded-full transition-all"
                        style={{
                          width: `${(count / (stats.total_archived || 1)) * 100}%`,
                        }}
                      />
                    </div>
                    <span className="w-12 text-sm text-muted-foreground text-right">{count}</span>
                  </div>
                ))}
              {!stats?.archive_level_counts && (
                <p className="text-muted-foreground text-center py-4">{t('archive.noArchiveData')}</p>
              )}
            </div>
          </div>

          {/* Quick Actions */}
          <div className="bg-card border border-border rounded-xl p-6">
            <h3 className="font-semibold mb-4">{t('archive.quickActions')}</h3>
            <div className="flex flex-wrap gap-3">
              <button
                onClick={handleAutoArchive}
                disabled={isProcessing}
                className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors"
              >
                <Archive className="w-4 h-4" />
                {isProcessing ? t('archive.processing') : t('archive.autoArchive')}
              </button>
              <button
                onClick={() => setActiveTab('duplicates')}
                className="flex items-center gap-2 px-4 py-2 bg-muted rounded-lg hover:bg-accent transition-colors"
              >
                <Search className="w-4 h-4" />
                {t('archive.detectDuplicates')}
              </button>
            </div>
            {processResult && (
              <div className="mt-4 p-3 bg-green-500/10 text-green-600 rounded-lg flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4" />
                {processResult}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Duplicates Tab */}
      {activeTab === 'duplicates' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold">
              {t('archive.duplicateGroups')} ({duplicates?.duplicate_groups?.length || 0})
            </h3>
            <button
              onClick={handleDetectDuplicates}
              disabled={isProcessing}
              className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors"
            >
              <Search className="w-4 h-4" />
              {isProcessing ? t('archive.detecting') : t('archive.reDetect')}
            </button>
          </div>

          {duplicates?.duplicate_groups?.length === 0 ? (
            <div className="text-center py-12">
              <CheckCircle2 className="w-16 h-16 text-green-500 mx-auto mb-4" />
              <h3 className="text-lg font-medium">{t('archive.noDuplicates')}</h3>
              <p className="text-muted-foreground mt-1">{t('archive.dedupDone')}</p>
            </div>
          ) : (
            <div className="space-y-4">
              {duplicates?.duplicate_groups?.map((group) => (
                <div key={group.group_id} className="bg-card border border-border rounded-xl p-4">
                  <div className="flex items-center justify-between mb-3">
                    <div>
                      <span className="text-sm font-medium">{t('archive.duplicateGroup')}</span>
                      <span className="text-xs text-muted-foreground ml-2">
                        {t('archive.memoriesCount', { count: group.memory_ids.length })}
                      </span>
                    </div>
                    <button
                      onClick={() => handleMergeGroup(group)}
                      disabled={isProcessing}
                      className="flex items-center gap-2 px-3 py-1.5 bg-primary text-primary-foreground text-sm rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors"
                    >
                      <Merge className="w-4 h-4" />
                      {t('archive.merge')}
                    </button>
                  </div>

                  <div className="space-y-2">
                    {group.memory_ids.map((id) => (
                      <div
                        key={id}
                        className={cn(
                          'flex items-center gap-3 p-2 rounded-lg',
                          id === group.canonical_id && 'bg-primary/5 border border-primary/20'
                        )}
                      >
                        <span className="text-sm font-medium">ID: {id}</span>
                        {id === group.canonical_id && (
                          <span className="text-xs px-2 py-0.5 bg-primary/10 text-primary rounded-full">
                            {t('archive.representative')}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>

                  {Object.keys(group.similarity_matrix).length > 0 && (
                    <div className="mt-3 pt-3 border-t border-border">
                      <p className="text-xs text-muted-foreground mb-2">{t('archive.similarityMatrix')}</p>
                      <div className="flex flex-wrap gap-2">
                        {Object.entries(group.similarity_matrix).map(([pair, score]) => (
                          <span key={pair} className="text-xs px-2 py-1 bg-muted rounded-full">
                            {pair}: {(score * 100).toFixed(1)}%
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Settings Tab */}
      {activeTab === 'settings' && (
        <div className="max-w-2xl">
          <div className="bg-card border border-border rounded-xl p-6 space-y-6">
            <h3 className="font-semibold">{t('archive.archiveSettings')}</h3>

            <div>
              <label className="text-sm font-medium mb-2 block">{t('archive.similarityThreshold')}</label>
              <p className="text-xs text-muted-foreground mb-3">
                {t('archive.similarityThresholdDesc')}
              </p>
              <input
                type="range"
                min="0.5"
                max="1"
                step="0.05"
                value={similarityThreshold}
                onChange={(e) => setSimilarityThreshold(parseFloat(e.target.value))}
                className="w-full"
              />
              <div className="flex justify-between text-xs text-muted-foreground mt-1">
                <span>0.5</span>
                <span>0.75</span>
                <span>1.0</span>
              </div>
            </div>

            <div>
              <label className="text-sm font-medium mb-2 block">{t('archive.autoArchiveDays')}</label>
              <p className="text-xs text-muted-foreground mb-3">{t('archive.autoArchiveDaysDesc')}</p>
              <select
                value={autoArchiveDays}
                onChange={(e) => setAutoArchiveDays(parseInt(e.target.value))}
                className="w-full px-3 py-2 bg-muted rounded-lg"
              >
                <option value="30">{t('archive.days', { count: 30 })}</option>
                <option value="60">{t('archive.days', { count: 60 })}</option>
                <option value="90">{t('archive.days', { count: 90 })}</option>
                <option value="180">{t('archive.days', { count: 180 })}</option>
              </select>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
