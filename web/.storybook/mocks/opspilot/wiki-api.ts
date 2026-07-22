import type { LlmModel } from '../../../src/app/opspilot/types/skill';
import type {
  GraphEdge,
  GraphNode,
  WikiGraph,
  WikiKnowledgeBase,
  WikiOverview,
  WikiQaResult,
} from '../../../src/app/opspilot/types/wiki';

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

// ── 概览 mock(贴齐截图:资料 2 / 页面 3 / 关系 7 / check 0 / 覆盖 100%) ──
const overviewFixture: WikiOverview = {
  knowledge_base: { id: 1, name: 'vfvfvfvf', status: 'active' },
  counts: { materials: 2, pages: 3, relations: 7, open_checks: 0 },
  contribution: { ai: 3 },
  material_status: { built: 2, done: 1, building: 1 },
  checks_by_type: {},
  health: { source_coverage: 100 },
  recent_pages: [
    { id: 11, title: '出差报销流程', contribution: 'AI 生成' },
    { id: 12, title: '财务部', contribution: 'AI 生成' },
    { id: 13, title: 'OA 系统', contribution: 'AI 生成' },
  ],
  recent_builds: [
    { id: 21, created_at: '2026-07-21T11:05:42+08:00', trigger: 'decision', status: 'success' },
    { id: 22, created_at: '2026-07-20T18:25:24+08:00', trigger: 'build', status: 'success' },
    { id: 23, created_at: '2026-07-20T18:15:50+08:00', trigger: 'build', status: 'success' },
    { id: 24, created_at: '2026-07-20T18:15:08+08:00', trigger: 'build', status: 'success' },
  ],
  agents: [],
};

// ── 多份变体概览 mock,用于覆盖左主内容 4 种状态 ──
const overviewEmpty: WikiOverview = {
  knowledge_base: { id: 1, name: 'vfvfvfvf', status: 'active' },
  counts: { materials: 0, pages: 0, relations: 0, open_checks: 0 },
  contribution: {},
  material_status: {},
  checks_by_type: {},
  health: { source_coverage: 0 },
  recent_pages: [],
  recent_builds: [],
  agents: [],
};

const overviewLowCoverage: WikiOverview = {
  knowledge_base: { id: 1, name: 'vfvfvfvf', status: 'active' },
  counts: { materials: 8, pages: 5, relations: 12, open_checks: 3 },
  contribution: { ai: 3, human: 2 },
  material_status: { built: 3, building: 2, failed: 1, pending: 2 },
  checks_by_type: { material_update: 2, duplicate: 1 },
  health: { source_coverage: 38 },
  recent_pages: [
    { id: 1, title: 'CMDB 资产录入流程', contribution: 'AI 生成' },
    { id: 2, title: '告警处理 SOP', contribution: 'AI 生成' },
    { id: 3, title: 'Kubernetes 部署规范', contribution: '人工' },
    { id: 4, title: '告警分页策略', contribution: 'AI 生成' },
    { id: 5, title: '巡检作业指导书', contribution: '人工' },
  ],
  recent_builds: [
    { id: 1, created_at: '2026-07-21T10:20:00+08:00', trigger: 'material_update', status: 'success' },
    { id: 2, created_at: '2026-07-21T09:15:00+08:00', trigger: 'rebuild', status: 'failed' },
    { id: 3, created_at: '2026-07-20T17:30:00+08:00', trigger: 'material', status: 'success' },
  ],
  agents: [
    { id: 1, name: '运维助手' },
    { id: 2, name: '故障排查 Agent' },
  ],
};

const overviewLots: WikiOverview = {
  knowledge_base: { id: 1, name: 'vfvfvfvf', status: 'active' },
  counts: { materials: 142, pages: 89, relations: 326, open_checks: 0 },
  contribution: { ai: 70, human: 19 },
  material_status: { built: 120, done: 18, building: 4 },
  checks_by_type: {},
  health: { source_coverage: 96 },
  recent_pages: [
    { id: 1, title: 'K8s 节点扩容标准操作', contribution: 'AI 生成' },
    { id: 2, title: 'MySQL 慢查询处理流程', contribution: 'AI 生成' },
    { id: 3, title: 'CMDB 资产录入流程', contribution: 'AI 生成' },
    { id: 4, title: 'Nginx 502 排查 SOP', contribution: 'AI 生成' },
    { id: 5, title: 'PaaS 部署规范 v2', contribution: '人工' },
    { id: 6, title: 'ES 集群扩容指南', contribution: 'AI 生成' },
    { id: 7, title: 'Redis 内存告警阈值', contribution: 'AI 生成' },
  ],
  recent_builds: [
    { id: 1, created_at: '2026-07-21T11:05:42+08:00', trigger: 'decision', status: 'success' },
    { id: 2, created_at: '2026-07-21T10:48:12+08:00', trigger: 'material_update', status: 'success' },
    { id: 3, created_at: '2026-07-21T09:30:00+08:00', trigger: 'rebuild', status: 'success' },
    { id: 4, created_at: '2026-07-20T22:15:00+08:00', trigger: 'material', status: 'success' },
    { id: 5, created_at: '2026-07-20T18:25:24+08:00', trigger: 'build', status: 'success' },
    { id: 6, created_at: '2026-07-20T18:15:50+08:00', trigger: 'build', status: 'success' },
    { id: 7, created_at: '2026-07-20T18:15:08+08:00', trigger: 'build', status: 'success' },
  ],
  agents: [
    { id: 1, name: '运维助手' },
    { id: 2, name: '故障排查 Agent' },
    { id: 3, name: '变更助手' },
    { id: 4, name: '新人 Onboarding 助手' },
  ],
};

// ── QA mock:按问题关键词返回不同答案 ──
const qaFixtureFor = (q: string): WikiQaResult => {
  if (/报销|reimbursement/i.test(q)) {
    return {
      answer:
        '出差报销流程:\n1. 员工在 OA 提交申请,填写出差时间、目的地、预算\n2. 直属主管审批(2 个工作日内)\n3. 财务复核,核对发票与预算\n4. 出纳支付,款项打入工资卡',
      citations: [
        { kind: 'page', id: 11, title: '出差报销流程' },
        { kind: 'page', id: 12, title: '财务部' },
      ],
      contexts: [],
    };
  }
  if (/OA|办公/i.test(q)) {
    return {
      answer: 'OA 系统包含流程审批、文档协作、考勤管理、报销管理 4 大核心模块。',
      citations: [{ kind: 'page', id: 13, title: 'OA 系统' }],
      contexts: [],
    };
  }
  if (/财务|finance/i.test(q)) {
    return {
      answer: '财务部负责公司日常财务核算、预算编制、税务申报与报销审核。',
      citations: [],
      contexts: [],
    };
  }
  if (/sla|时限|审批时长/i.test(q)) {
    return {
      answer:
        '主管审批 SLA:普通申请 2 个工作日内,紧急申请 4 小时内。超时自动升级到主管的上级。',
      citations: [{ kind: 'page', id: 11, title: '出差报销流程' }],
      contexts: [],
    };
  }
  return {
    answer: '这个问题在本知识库中没有直接答案,试试换成"报销""OA""财务"等关键词。',
    citations: [],
    contexts: [],
  };
};

const saveAnswerFixture = {
  id: 999,
  knowledge_base: 1,
  title: 'mock-saved',
  page_type: 'concept' as const,
  body: '',
  tags: [],
  contribution: 'AI 生成',
  status: 'draft',
};

export const useWikiApi = () => ({
  fetchKnowledgeBase: async () => delay(kb),
  updateKnowledgeBase: async (_id: number, data: Partial<WikiKnowledgeBase>) =>
    delay({ ...kb, ...data }),
  fetchLlmModels: async () => delay(models),
  rebuildKnowledgeBase: async () => delay({} as never),
  deleteKnowledgeBase: async () => delay(undefined),
  fetchGraphAnalysis: async () => delay(mockWikiGraph),
  rebuildRelations: async () => delay(mockWikiGraph),
  // 概览 + QA(补齐)
  // Storybook 通过 kbId 末位选择不同 fixture:1=默认 / 2=空 / 3=低覆盖 / 4=大量数据
  fetchOverview: async (id: number) => {
    const v = id % 10;
    if (v === 2) return delay(overviewEmpty);
    if (v === 3) return delay(overviewLowCoverage);
    if (v === 4) return delay(overviewLots);
    return delay(overviewFixture);
  },
  qa: async (_id: number, q: string) => delay(qaFixtureFor(q)),
  saveAnswerPage: async () => delay(saveAnswerFixture as never),
});

export default useWikiApi;
