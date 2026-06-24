import type { LlmModel } from '../../../src/app/opspilot/types/skill';
import type { WikiKnowledgeBase } from '../../../src/app/opspilot/types/wiki';

const kb: WikiKnowledgeBase = {
  id: 1,
  name: '运维知识库',
  introduction: '由 AI 持续构建、以页面为中心的运维知识库,支撑值班排障、变更与新人上手。',
  team: [1],
  team_name: ['Default'],
  llm_model: 1,
  purpose_md: '# Purpose\n\n## 目标\n沉淀可复用的运维知识,支撑值班、排障、变更与新人上手。',
  schema_md: '# Schema\n\n## 知识类型\n- 概念\n- 操作步骤\n- 故障案例',
  generation_language: 'zh',
  generation_rules: { notes: '统一术语表;每页包含「操作步骤」小节。' },
  web_sync_policy: { enabled: true, interval_hours: 24 },
  risk_rules: { auto_apply: true, require_review: false },
  template_key: 'general',
  status: 'active',
};

const models: LlmModel[] = [
  { id: 1, name: 'deepseek-v4-flash', enabled: true },
  { id: 2, name: 'gpt-4o', enabled: true },
  { id: 3, name: 'qwen-3-5-35b', enabled: true },
];

const delay = <T>(v: T) => new Promise<T>((r) => setTimeout(() => r(v), 200));

export const useWikiApi = () => ({
  fetchKnowledgeBase: async () => delay(kb),
  updateKnowledgeBase: async (_id: number, data: Partial<WikiKnowledgeBase>) => delay({ ...kb, ...data }),
  fetchLlmModels: async () => delay(models),
  rebuildKnowledgeBase: async () => delay({} as never),
  deleteKnowledgeBase: async () => delay(undefined),
});

export default useWikiApi;
