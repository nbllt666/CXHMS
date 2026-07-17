// ========== API 聚合入口 ==========
// 将各域 API 方法聚合为单一 `api` 对象，保持对原 `import { api } from '../api/client'`
// 调用方的向后兼容（仅改 import 路径为 '../api'，方法调用不变）。
// 新代码建议直接从具体域文件导入，如 `import { memoryApi } from '../api/memory'`。

import { commonApi } from './client';
import { memoryApi } from './memory';
import { chatApi } from './chat';
import { agentApi } from './agent';
import { graphApi } from './graph';
import { vectorApi } from './vector';
import { cxfcApi } from './cxfc';
import { configApi } from './config';

export const api = {
  ...commonApi,
  ...memoryApi,
  ...chatApi,
  ...agentApi,
  ...graphApi,
  ...vectorApi,
  ...cxfcApi,
  ...configApi,
};

// 重新导出各域，便于按域精确导入
export { commonApi } from './client';
export { memoryApi } from './memory';
export { chatApi } from './chat';
export { agentApi, type Agent } from './agent';
export type { AcpMessage } from './agent';
export { graphApi } from './graph';
export { vectorApi } from './vector';
export { cxfcApi } from './cxfc';
export { configApi } from './config';
// 基础设施
export { apiClient, controlClient, API_BASE_URL, CONTROL_SERVICE_URL } from './client';
// Task 9.4：重新导出 reinit / config reload 相关类型，供页面层使用
export type {
  ConfigDiff,
  ReinitResult,
  ReinitStatus,
  ReinitResponse,
  ConfigSaveResponse,
} from './client';
