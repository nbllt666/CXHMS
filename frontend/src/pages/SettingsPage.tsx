import { useState, useEffect, useCallback, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { api } from '../api';
import { cn } from '../lib/utils';
import { useThemeStore } from '../store/themeStore';
import { PageHeader } from '../components/layout';
import { Button, Card, CardBody } from '../components/ui';

interface SettingSection {
  id: string;
  title: string;
  icon: React.ReactNode;
  description: string;
}

export function SettingsPage() {
  const { t } = useTranslation();
  const [activeSection, setActiveSection] = useState<'appearance' | 'vector' | 'llm'>('appearance');
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const saveStatusTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [isBackendRunning, setIsBackendRunning] = useState(false);
  const [themeTransition, setThemeTransition] = useState(false);
  const [envManagedSections, setEnvManagedSections] = useState<{ vector: boolean; models: boolean }>(
    { vector: false, models: false }
  );

  const { theme, setTheme } = useThemeStore();
  const [selectedAccent, setSelectedAccent] = useState('#3b82f6');

  // 模块作用域数组移入组件以支持 i18n
  const sections: SettingSection[] = [
    {
      id: 'appearance',
      title: t('settings.appearanceSettings'),
      icon: (
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.657-1.657a2 2 0 012.828 0l2.829 2.829a2 2 0 010 2.828l-8.486 8.485M7 17h.01"
          />
        </svg>
      ),
      description: t('settings.appearanceSettingsDesc'),
    },
    {
      id: 'vector',
      title: t('settings.vectorStorage'),
      icon: (
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4"
          />
        </svg>
      ),
      description: t('settings.vectorStorageDesc'),
    },
    {
      id: 'llm',
      title: t('settings.modelSettings'),
      icon: (
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
          />
        </svg>
      ),
      description: t('settings.modelSettingsDesc'),
    },
  ];

  const themeOptions = [
    { value: 'light', label: t('settings.theme.light'), icon: '☀️', description: t('settings.themeLightDesc') },
    { value: 'dark', label: t('settings.theme.dark'), icon: '🌙', description: t('settings.themeDarkDesc') },
    { value: 'system', label: t('settings.theme.system'), icon: '💻', description: t('settings.themeSystemDesc') },
  ];

  const accentColors = [
    { value: '#3b82f6', label: t('settings.accentBlue'), class: 'bg-blue-500' },
    { value: '#8b5cf6', label: t('settings.accentPurple'), class: 'bg-violet-500' },
    { value: '#10b981', label: t('settings.accentGreen'), class: 'bg-emerald-500' },
    { value: '#f59e0b', label: t('settings.accentOrange'), class: 'bg-amber-500' },
    { value: '#ef4444', label: t('settings.accentRed'), class: 'bg-red-500' },
    { value: '#ec4899', label: t('settings.accentPink'), class: 'bg-pink-500' },
  ];

  useEffect(() => {
    document.documentElement.style.setProperty('--accent', selectedAccent);
  }, [selectedAccent]);

  const handleThemeChange = (newTheme: 'light' | 'dark' | 'system') => {
    setThemeTransition(true);
    setTheme(newTheme);
    setTimeout(() => setThemeTransition(false), 300);
  };

  const checkBackendStatus = useCallback(async () => {
    try {
      const status = await api.getMainBackendStatus();
      setIsBackendRunning(status.running);
      return status.running;
    } catch {
      setIsBackendRunning(false);
      return false;
    }
  }, []);

  useEffect(() => {
    checkBackendStatus();
    // F9: 健康检查轮询 3s → 15s，减少无谓周期请求
    const interval = setInterval(() => {
      checkBackendStatus();
    }, 15000);
    return () => clearInterval(interval);
  }, [checkBackendStatus]);

  useEffect(() => {
    return () => {
      if (saveStatusTimeoutRef.current) {
        clearTimeout(saveStatusTimeoutRef.current);
      }
    };
  }, []);

  const { data: serviceConfig } = useQuery({
    queryKey: ['serviceConfig'],
    queryFn: () => api.getServiceConfig(),
    enabled: isBackendRunning,
  });

  const [vectorConfig, setVectorConfig] = useState({
    backend: 'weaviate',
    vectorSize: 768,
    dbPath: 'data/chroma_db',
    collectionName: 'memory_vectors',
    weaviateHost: 'localhost',
    weaviatePort: 8090,
    qdrantHost: 'localhost',
    qdrantPort: 6333,
  });

  const [modelsConfig, setModelsConfig] = useState({
    main: {
      provider: 'vllm',
      host: 'http://localhost:8000',
      model: 'gemma4-e4b',
      apiKey: '',
      enabled: true,
    },
    summary: {
      provider: 'ollama',
      host: 'http://localhost:11434',
      model: 'qwen3-vl:8b',
      apiKey: '',
      enabled: false,
    },
    memory: {
      provider: 'ollama',
      host: 'http://localhost:11434',
      model: 'qwen3-vl:8b',
      apiKey: '',
      enabled: false,
    },
    embedding: {
      provider: 'vllm',
      host: 'http://localhost:8101',
      model: '/models/Qwen3-Embedding-0.6B',
      apiKey: '',
      enabled: true,
    },
  });

  const [modelDefaults, setModelDefaults] = useState({ summary: 'main', memory: 'main' });
  const [llmParams, setLlmParams] = useState({
    temperature: 0.7,
    max_tokens: 4096,
  });

  useEffect(() => {
    if (serviceConfig?.config) {
      if (serviceConfig.config.env_managed_sections) {
        setEnvManagedSections({
          vector: !!serviceConfig.config.env_managed_sections.vector,
          models: !!serviceConfig.config.env_managed_sections.models,
        });
      }
      if (serviceConfig.config.vector) {
        const vec = serviceConfig.config.vector;
        setVectorConfig({
          backend: vec.backend ?? 'weaviate',
          vectorSize: vec.vector_size ?? 2048,
          dbPath: vec.db_path ?? 'data/chroma_db',
          collectionName: vec.collection_name ?? 'memory_vectors',
          weaviateHost: vec.weaviate_host ?? 'localhost',
          weaviatePort: vec.weaviate_port ?? 8090,
          qdrantHost: vec.qdrant_host ?? 'localhost',
          qdrantPort: vec.qdrant_port ?? 6333,
        });
      }
      if (serviceConfig.config.models) {
        setModelsConfig((prev) => ({
          main: serviceConfig.config.models?.main
            ? { ...prev.main, ...serviceConfig.config.models.main }
            : prev.main,
          summary: serviceConfig.config.models?.summary
            ? { ...prev.summary, ...serviceConfig.config.models.summary }
            : prev.summary,
          memory: serviceConfig.config.models?.memory
            ? { ...prev.memory, ...serviceConfig.config.models.memory }
            : prev.memory,
          embedding: serviceConfig.config.models?.embedding
            ? { ...prev.embedding, ...serviceConfig.config.models.embedding }
            : prev.embedding,
        }));
      }
      if (serviceConfig.config.model_defaults) {
        setModelDefaults({
          summary: serviceConfig.config.model_defaults.summary ?? 'main',
          memory: serviceConfig.config.model_defaults.memory ?? 'main',
        });
      }
      if (serviceConfig.config.llm_params) {
        setLlmParams({
          temperature: serviceConfig.config.llm_params.temperature ?? 0.7,
          max_tokens: serviceConfig.config.llm_params.max_tokens ?? 4096,
        });
      }
    }
  }, [serviceConfig]);

  useEffect(() => {
    if (activeSection === 'vector' && envManagedSections.vector) {
      setActiveSection('appearance');
    } else if (activeSection === 'llm' && envManagedSections.models) {
      setActiveSection('appearance');
    }
  }, [activeSection, envManagedSections]);

  const handleSave = async () => {
    if (!isBackendRunning) {
      alert(t('settings.backendNotRunning'));
      return;
    }
    if (activeSection === 'vector' && envManagedSections.vector) {
      alert(t('settings.vectorEnvManagedAlert'));
      return;
    }
    if (activeSection === 'llm' && envManagedSections.models) {
      alert(t('settings.modelEnvManagedAlert'));
      return;
    }
    setSaveStatus('saving');
    try {
      if (activeSection === 'vector') {
        const vectorPayload: Record<string, unknown> = {
          backend: vectorConfig.backend,
          vector_size: vectorConfig.vectorSize,
        };

        if (vectorConfig.backend === 'chroma') {
          vectorPayload.db_path = vectorConfig.dbPath;
          vectorPayload.collection_name = vectorConfig.collectionName;
        } else if (vectorConfig.backend === 'milvus_lite') {
          vectorPayload.db_path = vectorConfig.dbPath;
        } else if (
          vectorConfig.backend === 'weaviate' ||
          vectorConfig.backend === 'weaviate_embedded'
        ) {
          vectorPayload.weaviate_host = vectorConfig.weaviateHost;
          vectorPayload.weaviate_port = vectorConfig.weaviatePort;
        } else if (vectorConfig.backend === 'qdrant') {
          vectorPayload.qdrant_host = vectorConfig.qdrantHost;
          vectorPayload.qdrant_port = vectorConfig.qdrantPort;
        }

        await api.updateServiceConfig({
          vector: vectorPayload,
        });
      } else if (activeSection === 'llm') {
        await api.updateServiceConfig({
          models: modelsConfig,
          model_defaults: modelDefaults,
          llm_params: llmParams,
        });
        localStorage.setItem('cxhms-current-model', modelsConfig.main.model);
      }
      setSaveStatus('saved');
    } catch {
      setSaveStatus('error');
    }
    saveStatusTimeoutRef.current = setTimeout(() => setSaveStatus('idle'), 2000);
  };

  const visibleSections = sections.filter((section) => {
    if (section.id === 'vector' && envManagedSections.vector) return false;
    if (section.id === 'llm' && envManagedSections.models) return false;
    return true;
  });

  return (
    <div className={`max-w-6xl mx-auto ${themeTransition ? 'transition-colors duration-300' : ''}`}>
      <PageHeader title={t('settings.title')} description={t('settings.pageDescription')} />

      <div className="flex gap-6">
        <nav className="w-56 flex-shrink-0 space-y-1">
          {visibleSections.map((section) => (
            <button
              key={section.id}
              onClick={() => setActiveSection(section.id as typeof activeSection)}
              className={cn(
                'w-full flex items-center gap-3 px-3 py-2.5 rounded-[var(--radius-lg)] text-sm font-medium transition-colors text-left',
                activeSection === section.id
                  ? 'bg-[var(--color-accent-light)] text-[var(--color-accent)]'
                  : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-hover)] hover:text-[var(--color-text-primary)]'
              )}
            >
              {section.icon}
              <div>
                <div>{section.title}</div>
                <div className="text-xs text-[var(--color-text-tertiary)] font-normal">
                  {section.description}
                </div>
              </div>
            </button>
          ))}
        </nav>

        <div className="flex-1 min-w-0">
          {activeSection === 'appearance' && (
            <div className="space-y-6">
              <Card>
                <CardBody>
                  <h3 className="text-lg font-semibold mb-4">{t('settings.themeSettings')}</h3>
                  <div className="grid grid-cols-3 gap-4">
                    {themeOptions.map((option) => (
                      <button
                        key={option.value}
                        onClick={() => handleThemeChange(option.value as typeof theme)}
                        className={cn(
                          'p-4 rounded-[var(--radius-lg)] border-2 transition-all text-left',
                          theme === option.value
                            ? 'border-[var(--color-accent)] bg-[var(--color-accent-light)]'
                            : 'border-[var(--color-border)] hover:border-[var(--color-accent)]/50'
                        )}
                      >
                        <div className="text-2xl mb-2">{option.icon}</div>
                        <div className="font-medium">{option.label}</div>
                        <div className="text-xs text-[var(--color-text-tertiary)]">
                          {option.description}
                        </div>
                      </button>
                    ))}
                  </div>
                </CardBody>
              </Card>

              <Card>
                <CardBody>
                  <h3 className="text-lg font-semibold mb-4">{t('settings.accentColor')}</h3>
                  <div className="flex gap-3">
                    {accentColors.map((color) => (
                      <button
                        key={color.value}
                        onClick={() => setSelectedAccent(color.value)}
                        className={cn(
                          'w-10 h-10 rounded-full transition-all',
                          color.class,
                          selectedAccent === color.value
                            ? 'ring-2 ring-offset-2 ring-[var(--color-accent)] scale-110'
                            : 'hover:scale-105'
                        )}
                        title={color.label}
                      />
                    ))}
                  </div>
                  <p className="text-xs text-[var(--color-text-tertiary)] mt-3">
                    {t('settings.accentColorDesc')}
                  </p>
                </CardBody>
              </Card>

              <Card>
                <CardBody>
                  <h3 className="text-lg font-semibold mb-4">{t('settings.connectionSettings')}</h3>
                  <div className="space-y-4">
                    <div>
                      <label className="block text-sm font-medium mb-2">{t('settings.offlineTimeoutLabel')}</label>
                      <p className="text-xs text-[var(--color-text-tertiary)] mb-3">
                        {t('settings.offlineTimeoutDesc')}
                      </p>
                      <select
                        value={localStorage.getItem('cxhms-offline-timeout') || '60'}
                        onChange={(e) => {
                          localStorage.setItem('cxhms-offline-timeout', e.target.value);
                          window.dispatchEvent(
                            new CustomEvent('offline-timeout-change', { detail: e.target.value })
                          );
                        }}
                        className="w-full px-3 py-2 bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] rounded-[var(--radius-md)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
                      >
                        <option value="30">{t('settings.timeout30s')}</option>
                        <option value="60">{t('settings.timeout60s')}</option>
                        <option value="120">{t('settings.timeout2min')}</option>
                        <option value="300">{t('settings.timeout5min')}</option>
                      </select>
                    </div>
                  </div>
                </CardBody>
              </Card>

              <Card>
                <CardBody>
                  <h3 className="text-lg font-semibold mb-4">{t('settings.interfacePreview')}</h3>
                  <div className="p-4 bg-[var(--color-bg-tertiary)] rounded-[var(--radius-lg)]">
                    <div className="flex items-center gap-3 mb-4">
                      <div className="w-10 h-10 rounded-full bg-[var(--color-accent)] flex items-center justify-center text-[var(--color-bg-primary)]">
                        AI
                      </div>
                      <div>
                        <div className="font-medium">{t('settings.sampleTitle')}</div>
                        <div className="text-sm text-[var(--color-text-secondary)]">
                          {t('settings.sampleText')}
                        </div>
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <Button size="sm">{t('settings.primaryButton')}</Button>
                      <Button variant="secondary" size="sm">
                        {t('settings.secondaryButton')}
                      </Button>
                      <Button variant="ghost" size="sm">
                        {t('settings.ghostButton')}
                      </Button>
                    </div>
                  </div>
                </CardBody>
              </Card>
            </div>
          )}

          {activeSection === 'vector' && envManagedSections.vector && (
            <Card>
              <CardBody>
                <h3 className="text-lg font-semibold mb-2">{t('settings.vectorConfigTitle')}</h3>
                <p className="text-sm text-[var(--color-text-secondary)]">
                  {t('settings.vectorEnvManaged')}
                </p>
              </CardBody>
            </Card>
          )}

          {activeSection === 'vector' && !envManagedSections.vector && (
            <div className="space-y-6">
              <Card>
                <CardBody>
                  <h3 className="text-lg font-semibold mb-4">{t('settings.vectorConfigTitle')}</h3>
                  <div className="space-y-4">
                    <div>
                      <label className="text-sm font-medium mb-2 block">{t('settings.vectorBackendLabel')}</label>
                      <select
                        value={vectorConfig.backend}
                        onChange={(e) =>
                          setVectorConfig({ ...vectorConfig, backend: e.target.value })
                        }
                        className="w-full px-3 py-2 bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-[var(--radius-md)]"
                      >
                        <option value="chroma">{t('settings.backendChroma')}</option>
                        <option value="milvus_lite">{t('settings.backendMilvusLite')}</option>
                        <option value="weaviate_embedded">{t('settings.backendWeaviateEmbedded')}</option>
                        <option value="weaviate">{t('settings.backendWeaviate')}</option>
                        <option value="qdrant">{t('settings.backendQdrant')}</option>
                      </select>
                    </div>
                    <div>
                      <label className="text-sm font-medium mb-2 block">{t('settings.vectorDimLabel')}</label>
                      <select
                        value={vectorConfig.vectorSize}
                        onChange={(e) =>
                          setVectorConfig({ ...vectorConfig, vectorSize: parseInt(e.target.value) })
                        }
                        className="w-full px-3 py-2 bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-[var(--radius-md)]"
                      >
                        <option value={384}>{t('settings.dimSmall')}</option>
                        <option value={768}>{t('settings.dimMedium')}</option>
                        <option value={1024}>{t('settings.dimLarge')}</option>
                        <option value={1536}>{t('settings.dimOpenai')}</option>
                        <option value={2048}>{t('settings.dimXlarge')}</option>
                      </select>
                    </div>
                    {vectorConfig.backend === 'chroma' && (
                      <div>
                        <label className="text-sm font-medium mb-2 block">{t('settings.dataPathLabel')}</label>
                        <input
                          type="text"
                          value={vectorConfig.dbPath || 'data/chroma_db'}
                          onChange={(e) =>
                            setVectorConfig({ ...vectorConfig, dbPath: e.target.value })
                          }
                          className="w-full px-3 py-2 bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-[var(--radius-md)]"
                          placeholder="data/chroma_db"
                        />
                      </div>
                    )}
                    {(vectorConfig.backend === 'weaviate' ||
                      vectorConfig.backend === 'weaviate_embedded') && (
                      <>
                        <div>
                          <label className="text-sm font-medium mb-2 block">{t('settings.weaviateHostLabel')}</label>
                          <input
                            type="text"
                            value={vectorConfig.weaviateHost || 'localhost'}
                            onChange={(e) =>
                              setVectorConfig({ ...vectorConfig, weaviateHost: e.target.value })
                            }
                            className="w-full px-3 py-2 bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-[var(--radius-md)]"
                            placeholder="localhost"
                          />
                        </div>
                        <div>
                          <label className="text-sm font-medium mb-2 block">{t('settings.weaviatePortLabel')}</label>
                          <input
                            type="number"
                            value={vectorConfig.weaviatePort || 8080}
                            onChange={(e) =>
                              setVectorConfig({
                                ...vectorConfig,
                                weaviatePort: parseInt(e.target.value),
                              })
                            }
                            className="w-full px-3 py-2 bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-[var(--radius-md)]"
                            placeholder="8080"
                          />
                        </div>
                      </>
                    )}
                    {vectorConfig.backend === 'qdrant' && (
                      <>
                        <div>
                          <label className="text-sm font-medium mb-2 block">{t('settings.qdrantHostLabel')}</label>
                          <input
                            type="text"
                            value={vectorConfig.qdrantHost || 'localhost'}
                            onChange={(e) =>
                              setVectorConfig({ ...vectorConfig, qdrantHost: e.target.value })
                            }
                            className="w-full px-3 py-2 bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-[var(--radius-md)]"
                            placeholder="localhost"
                          />
                        </div>
                        <div>
                          <label className="text-sm font-medium mb-2 block">{t('settings.qdrantPortLabel')}</label>
                          <input
                            type="number"
                            value={vectorConfig.qdrantPort || 6333}
                            onChange={(e) =>
                              setVectorConfig({
                                ...vectorConfig,
                                qdrantPort: parseInt(e.target.value),
                              })
                            }
                            className="w-full px-3 py-2 bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-[var(--radius-md)]"
                            placeholder="6333"
                          />
                        </div>
                      </>
                    )}
                  </div>
                  <div className="flex justify-end mt-6">
                    <Button
                      onClick={handleSave}
                      loading={saveStatus === 'saving'}
                      disabled={!isBackendRunning}
                    >
                      {saveStatus === 'saved' ? t('settings.savedLabel') : t('settings.saveConfig')}
                    </Button>
                  </div>
                </CardBody>
              </Card>
            </div>
          )}

          {activeSection === 'llm' && envManagedSections.models && (
            <Card>
              <CardBody>
                <h3 className="text-lg font-semibold mb-2">{t('settings.modelConfigTitle')}</h3>
                <p className="text-sm text-[var(--color-text-secondary)]">
                  {t('settings.modelEnvManaged')}
                </p>
              </CardBody>
            </Card>
          )}

          {activeSection === 'llm' && !envManagedSections.models && (
            <div className="space-y-6">
              <Card>
                <CardBody>
                  <h3 className="text-lg font-semibold mb-4">{t('settings.modelConfigTitle')}</h3>
                  <div className="space-y-4">
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="text-sm font-medium mb-2 block">{t('settings.modelProviderLabel')}</label>
                        <select
                          value={modelsConfig.main.provider}
                          onChange={(e) =>
                            setModelsConfig((prev) => ({
                              ...prev,
                              main: { ...prev.main, provider: e.target.value },
                            }))
                          }
                          className="w-full px-3 py-2 bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-[var(--radius-md)]"
                        >
                          <option value="ollama">{t('settings.providerOllama')}</option>
                          <option value="vllm">{t('settings.providerVllm')}</option>
                          <option value="openai">{t('settings.providerOpenai')}</option>
                        </select>
                      </div>
                      <div>
                        <label className="text-sm font-medium mb-2 block">{t('settings.modelNameLabel')}</label>
                        <input
                          type="text"
                          value={modelsConfig.main.model}
                          onChange={(e) =>
                            setModelsConfig((prev) => ({
                              ...prev,
                              main: { ...prev.main, model: e.target.value },
                            }))
                          }
                          className="w-full px-3 py-2 bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-[var(--radius-md)]"
                        />
                      </div>
                    </div>
                    <div>
                      <label className="text-sm font-medium mb-2 block">
                        {t('settings.temperatureLabel')}: {llmParams.temperature}
                      </label>
                      <input
                        type="range"
                        min="0"
                        max="2"
                        step="0.1"
                        value={llmParams.temperature}
                        onChange={(e) =>
                          setLlmParams({ ...llmParams, temperature: parseFloat(e.target.value) })
                        }
                        className="w-full"
                      />
                    </div>
                    <div className="border-t border-[var(--color-border)] pt-4 mt-4">
                      <h4 className="text-md font-medium mb-3">{t('settings.embeddingSectionTitle')}</h4>
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="text-sm font-medium mb-2 block">{t('settings.embeddingProviderLabel')}</label>
                          <select
                            value={modelsConfig.embedding.provider}
                            onChange={(e) =>
                              setModelsConfig((prev) => ({
                                ...prev,
                                embedding: { ...prev.embedding, provider: e.target.value },
                              }))
                            }
                            className="w-full px-3 py-2 bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-[var(--radius-md)]"
                          >
                            <option value="ollama">{t('settings.providerOllama')}</option>
                            <option value="vllm">{t('settings.providerVllm')}</option>
                            <option value="openai">{t('settings.providerOpenai')}</option>
                          </select>
                        </div>
                        <div>
                          <label className="text-sm font-medium mb-2 block">{t('settings.embeddingNameLabel')}</label>
                          <input
                            type="text"
                            value={modelsConfig.embedding.model}
                            onChange={(e) =>
                              setModelsConfig((prev) => ({
                                ...prev,
                                embedding: { ...prev.embedding, model: e.target.value },
                              }))
                            }
                            className="w-full px-3 py-2 bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-[var(--radius-md)]"
                            placeholder="/models/Qwen3-Embedding-0.6B"
                          />
                        </div>
                      </div>
                      <div className="mt-4">
                        <label className="text-sm font-medium mb-2 block">{t('settings.embeddingUrlLabel')}</label>
                        <input
                          type="text"
                          value={modelsConfig.embedding.host}
                          onChange={(e) =>
                            setModelsConfig((prev) => ({
                              ...prev,
                              embedding: { ...prev.embedding, host: e.target.value },
                            }))
                          }
                          className="w-full px-3 py-2 bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-[var(--radius-md)]"
                          placeholder="http://localhost:8101"
                        />
                      </div>
                    </div>
                  </div>
                  <div className="flex justify-end mt-6">
                    <Button
                      onClick={handleSave}
                      loading={saveStatus === 'saving'}
                      disabled={!isBackendRunning}
                    >
                      {saveStatus === 'saved' ? t('settings.savedLabel') : t('settings.saveConfig')}
                    </Button>
                  </div>
                </CardBody>
              </Card>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
