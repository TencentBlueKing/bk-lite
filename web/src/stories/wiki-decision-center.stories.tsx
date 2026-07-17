import type { Meta, StoryObj } from '@storybook/nextjs';
import { fn } from 'storybook/test';
import WikiDecisionCenter from '@/app/opspilot/components/wiki/WikiDecisionCenter';
import type { CheckItem } from '@/app/opspilot/types/wiki';

const knowledgeConflict: CheckItem = {
  id: 1001,
  knowledge_base: 12,
  check_type: 'material_update',
  decision_type: 'knowledge_conflict',
  status: 'open',
  created_at: '2026-07-14T10:20:00+08:00',
  candidate_version: 13,
  related_pages: [
    {
      id: 201,
      title: 'Kubernetes 节点磁盘告警阈值',
      page_type: '运维规则',
      body: '## 告警条件\n\n节点磁盘使用率达到阈值，并连续 3 次采集超过阈值时触发。\n\n- 节点磁盘使用率达到 **80%** 时触发告警。\n\n处置前至少保留最近 7 天的业务日志。',
      version_label: '当前 v12',
      source_count: 3,
      relation_count: 3,
    },
  ],
  candidate: {
    id: 301,
    body: '## 告警条件\n\n节点磁盘使用率达到阈值，并持续 5 分钟超过阈值时触发。\n\n- 节点磁盘使用率达到 **85%** 时触发告警。\n\n处置前至少保留最近 7 天的业务日志。',
  },
  decision_context: {
    title: 'Kubernetes 节点磁盘告警阈值',
    summary: '新资料将告警阈值从 80% 调整为 85%，与当前知识不一致',
    reason: '关键结论发生变化',
    current_source_label: 'Kubernetes 运维手册 v2025.12',
    incoming_source_label: 'SRE 运行标准 v2026.06',
    trigger_source: 'SRE 运行标准 v2026.06',
    impact_scope: '1 个页面 · 3 条关系 · 8 个分块',
    recoverability: '旧版本保留，可随时恢复',
  },
};

const pageIdentity: CheckItem = {
  id: 1002,
  knowledge_base: 12,
  check_type: 'duplicate',
  decision_type: 'page_identity',
  status: 'open',
  created_at: '2026-07-13T16:42:00+08:00',
  related_pages: [
    {
      id: 202,
      title: '配置平台',
      page_type: '实体',
      body: '统一管理业务、主机、服务实例与模型关系，是资产数据的主要事实来源。',
      contribution: '人工维护',
      source_count: 3,
      relation_count: 4,
      version_label: '当前知识',
    },
    {
      id: 203,
      title: 'CMDB',
      page_type: '实体',
      body: '配置管理数据库，用于记录基础设施资源、属性以及资源之间的关联。',
      contribution: 'AI 生成',
      source_count: 1,
      relation_count: 2,
      version_label: '新知识',
    },
  ],
  current_knowledge: {
    id: 202,
    page_id: 202,
    title: '配置平台',
    page_type: '实体',
    body: '统一管理业务、主机、服务实例与模型关系，是资产数据的主要事实来源。',
    contribution: '人工维护',
    source_count: 3,
    relation_count: 4,
    version_label: '当前知识',
  },
  new_knowledge: {
    id: 203,
    page_id: 203,
    title: 'CMDB',
    page_type: '实体',
    body: '配置管理数据库，用于记录基础设施资源、属性以及资源之间的关联。',
    contribution: 'AI 生成',
    source_count: 1,
    relation_count: 2,
    version_label: '新知识',
  },
  decision_context: {
    page_identities: [
      {
        page_id: 202,
        title: '配置平台',
        page_type: '实体',
        canonical_title: '配置平台',
        canonical_title_key: '配置平台',
        compact_title_key: '配置平台',
        body_hash: 'sha256:configuration-platform',
      },
      {
        page_id: 203,
        title: 'CMDB',
        page_type: '实体',
        canonical_title: 'cmdb',
        canonical_title_key: 'cmdb',
        compact_title_key: 'cmdb',
        body_hash: 'sha256:cmdb',
      },
    ],
    target_identity: {
      page_id: 202,
      title: '配置平台',
      page_type: '实体',
      canonical_title: '配置平台',
      canonical_title_key: '配置平台',
      compact_title_key: '配置平台',
      body_hash: 'sha256:configuration-platform',
    },
    title: '“CMDB”与“配置平台”可能是同一知识',
    summary: '标题别名、页面类型与核心内容高度一致，需要确认知识边界',
    reason: '身份相同但系统无法确认',
    trigger_source: '资产管理规范 / 平台介绍',
    impact_scope: '2 个页面 · 5 条关系 · 4 份证据',
    recoverability: '来源页面归档，可随时恢复',
  },
};

const automaticReplay: CheckItem = {
  ...knowledgeConflict,
  id: 1003,
  status: 'resolved',
  decision_action: 'use_new',
  decision_operator: 'admin',
  decision_processed_at: '2026-07-14T09:15:00+08:00',
  decision_rule: {
    id: 501,
    status: 'active',
    action: 'use_new',
    match_snapshot: {},
    result_snapshot: {},
    replay_count: 4,
    last_replayed_at: '2026-07-14T09:30:00+08:00',
  },
};

const revokedRule: CheckItem = {
  ...pageIdentity,
  id: 1004,
  status: 'dismissed',
  decision_action: 'keep_separate',
  decision_operator: 'wiki-owner',
  decision_processed_at: '2026-07-13T17:05:00+08:00',
  decision_rule: {
    id: 502,
    status: 'revoked',
    action: 'keep_separate',
    match_snapshot: {},
    result_snapshot: {},
    replay_count: 2,
    last_replayed_at: '2026-07-13T18:10:00+08:00',
    revoked_reason: 'page_identity_changed',
  },
};

const meta = {
  title: 'OpsPilot/WikiDecisionCenter',
  component: WikiDecisionCenter,
  parameters: { layout: 'fullscreen' },
  decorators: [
    (Story) => (
      <div className="min-h-screen bg-[var(--color-primary-bg-active)] p-4 lg:p-6">
        <Story />
      </div>
    ),
  ],
  args: {
    total: 1,
    page: 1,
    pageSize: 20,
    onViewChange: fn(),
    onSelect: fn(),
    onPageChange: fn(),
    onDecide: fn(),
    onRevoke: fn(),
    onRefresh: fn(),
  },
} satisfies Meta<typeof WikiDecisionCenter>;

export default meta;
type Story = StoryObj<typeof meta>;

export const KnowledgeConflict: Story = {
  args: {
    items: [knowledgeConflict],
    view: 'pending',
    pendingCount: 1,
    processedCount: 0,
    activeId: knowledgeConflict.id,
  },
};

export const PageIdentityMerge: Story = {
  args: {
    items: [pageIdentity],
    view: 'pending',
    pendingCount: 1,
    processedCount: 0,
    activeId: pageIdentity.id,
  },
};

export const AutomaticReplay: Story = {
  args: {
    items: [automaticReplay],
    view: 'processed',
    pendingCount: 0,
    processedCount: 1,
    activeId: automaticReplay.id,
  },
};

export const RevokedRule: Story = {
  args: {
    items: [revokedRule],
    view: 'processed',
    pendingCount: 0,
    processedCount: 1,
    activeId: revokedRule.id,
  },
};
