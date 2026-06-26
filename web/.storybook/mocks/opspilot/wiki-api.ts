import type { LlmModel } from '../../../src/app/opspilot/types/skill';
import type { GraphEdge, GraphNode, WikiGraph, WikiKnowledgeBase } from '../../../src/app/opspilot/types/wiki';

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

// ── 关系图谱 mock 数据(蓝鲸平台主题:两大社区 + 3 个孤立节点用于演示过滤) ──
const nodes: GraphNode[] = [
  { id: 1, title: '蓝鲸平台 (BlueKing)', page_type: '实体', community: 0 },
  { id: 5, title: 'ESB (企业服务总线)', page_type: '实体', community: 0 },
  { id: 7, title: '蓝鲸平台介绍', page_type: '概述', community: 0 },
  { id: 8, title: '蓝鲸组件依赖关系', page_type: '概念', community: 0 },
  { id: 9, title: '运维自动化 (IT Operation Automation)', page_type: '概念', community: 0 },
  { id: 13, title: '监控平台', page_type: '实体', community: 0 },
  { id: 2, title: 'PaaS (开发者中心)', page_type: '实体', community: 1 },
  { id: 3, title: 'JOB (作业平台)', page_type: '实体', community: 1 },
  { id: 4, title: 'BKDATA (数据平台)', page_type: '实体', community: 1 },
  { id: 6, title: '蓝鲸分层架构', page_type: '概念', community: 1 },
  { id: 14, title: '标准运维', page_type: '实体', community: 1 },
  { id: 10, title: 'CMDB (配置平台)', page_type: '实体', community: 2 },
  { id: 11, title: 'GSE (管控平台)', page_type: '来源', community: 3 },
  { id: 12, title: 'Research Log', page_type: '其他', community: 4 },
];

const e = (from: number, to: number, weight: number, signals: Record<string, number> = { wikilink: 1 }): GraphEdge => ({
  from,
  to,
  weight,
  signals,
});

const edges: GraphEdge[] = [
  // 社区 0 内部
  e(1, 5, 1.5),
  e(1, 7, 1.8, { wikilink: 1, shared_source: 1 }),
  e(1, 8, 1.6),
  e(1, 9, 1.2),
  e(7, 8, 1.3),
  e(8, 13, 1.1),
  e(1, 13, 1.4),
  // 社区 1 内部
  e(2, 3, 1.7, { wikilink: 1, reference: 1 }),
  e(2, 4, 1.6),
  e(2, 6, 1.5),
  e(6, 14, 1.2),
  e(2, 14, 1.3),
  e(3, 14, 1.1),
  // 跨社区(意外连接)
  e(1, 2, 2.0, { wikilink: 1, reference: 1, shared_source: 1 }),
  e(7, 6, 1.4),
  e(8, 2, 1.3),
  e(3, 1, 1.5),
  e(9, 2, 1.2),
  // 10/11/12 故意保留为孤立节点
];

const strongest_edges = [...edges].sort((a, b) => (b.weight || 0) - (a.weight || 0)).slice(0, 6);

export const mockWikiGraph: WikiGraph = {
  nodes,
  edges,
  communities: [[1, 5, 7, 8, 9, 13], [2, 3, 4, 6, 14], [10], [11], [12]],
  insights: {
    node_count: nodes.length,
    edge_count: edges.length,
    community_count: 5,
    largest_community: 6,
    strongest_edges,
  },
};

const delay = <T>(v: T) => new Promise<T>((r) => setTimeout(() => r(v), 200));

export const useWikiApi = () => ({
  fetchKnowledgeBase: async () => delay(kb),
  updateKnowledgeBase: async (_id: number, data: Partial<WikiKnowledgeBase>) => delay({ ...kb, ...data }),
  fetchLlmModels: async () => delay(models),
  rebuildKnowledgeBase: async () => delay({} as never),
  deleteKnowledgeBase: async () => delay(undefined),
  fetchGraphAnalysis: async () => delay(mockWikiGraph),
  rebuildRelations: async () => delay(mockWikiGraph),
});

export default useWikiApi;
