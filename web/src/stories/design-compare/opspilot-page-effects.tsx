'use client';

/**
 * OpsPilot 24-page After effects — craft pass.
 * Unified list system + LangSmith/Linear/Datadog-inspired density under OpsPilot tokens.
 */

import type { ReactNode } from 'react';
import {
  Button,
  Col,
  Collapse,
  Dropdown,
  Empty,
  Form,
  Input,
  Menu,
  Progress,
  Row,
  Segmented,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Tree,
  Typography,
} from 'antd';
import { CaretRightOutlined, DownOutlined } from '@ant-design/icons';
import {
  BeautifulInsightStrip,
  PageEffectFrame,
  UnifiedFilterChips,
  UnifiedListChrome,
  UnifiedOpsCard,
  useListFilter,
  afterSys,
  type UnifiedOpsCardProps,
} from './opspilot-after-system';
import {
  OpsPilotChatWorkspace,
  OpsPilotConversationDemo,
} from './opspilot-conversation';
import { PageSkillSettings as SkillSettingsWorkbench } from './opspilot-skill-settings-effect';
import {
  MemoryConfigWorkbench,
  MemoryMemoriesWorkbench,
  SettingsManageWorkbench,
  SettingsQuotaWorkbench,
} from './opspilot-memory-settings-effect';
import { ProviderDetailWorkbench } from './opspilot-provider-detail-effect';
import {
  AfterEntityShell,
  MEMORY_NAV,
  SKILL_NAV,
  STUDIO_NAV,
  WIKI_NAV,
} from './opspilot-entity-shell';

const { Text, Title, Paragraph } = Typography;

function TaskRowsPolished() {
  const rows = [
    { title: '校验集群凭据', meta: '12 targets', status: 'Completed', progress: 100 },
    { title: '匹配工作负载', meta: '12/12', status: 'Completed', progress: 100 },
    { title: '构建补丁任务', meta: '7 workloads', status: 'Running', progress: 62 },
    { title: '草拟变更说明', meta: '2 drafts', status: 'Queued', progress: 0 },
  ];
  return (
    <div style={{ border: afterSys.border, borderRadius: afterSys.radius, overflow: 'hidden', background: afterSys.bg }}>
      <div
        style={{
          padding: '8px 12px',
          background: afterSys.fill,
          borderBottom: afterSys.borderSoft,
          fontSize: 11,
          color: afterSys.text4,
          fontFamily: afterSys.mono,
          display: 'flex',
          justifyContent: 'space-between',
        }}
      >
        <span>task rows</span>
        <span>1 running</span>
      </div>
      {rows.map((r, i) => (
        <div
          key={r.title}
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr auto',
            gap: 8,
            padding: '10px 12px',
            borderTop: i === 0 ? undefined : afterSys.borderSoft,
          }}
        >
          <div>
            <div style={{ fontSize: 13, color: afterSys.text1 }}>{r.title}</div>
            <div style={{ fontSize: 11.5, color: afterSys.text4, marginTop: 2 }}>{r.meta}</div>
            {r.status === 'Running' && (
              <Progress
                percent={r.progress}
                size="small"
                showInfo={false}
                strokeColor={afterSys.primary}
                style={{ marginTop: 6, marginBottom: 0 }}
              />
            )}
          </div>
          <StatusQuiet label={r.status} tone={r.status === 'Completed' ? 'ok' : r.status === 'Running' ? 'run' : 'mute'} />
        </div>
      ))}
    </div>
  );
}

function StatusQuiet({ label, tone }: { label: string; tone: 'ok' | 'run' | 'mute' | 'bad' }) {
  const color =
    tone === 'ok' ? afterSys.success : tone === 'run' ? afterSys.primary : tone === 'bad' ? afterSys.fail : afterSys.text4;
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 5,
        height: 22,
        padding: '0 8px',
        borderRadius: 999,
        fontSize: 11,
        color: afterSys.text2,
        background: afterSys.fill,
        alignSelf: 'start',
        flexShrink: 0,
      }}
    >
      <span style={{ width: 6, height: 6, borderRadius: 999, background: color }} />
      {label}
    </span>
  );
}

function Panel({ children, title, extra }: { children: ReactNode; title?: string; extra?: ReactNode }) {
  return (
    <div style={{ border: afterSys.border, borderRadius: afterSys.radius, background: afterSys.bg, overflow: 'hidden' }}>
      {(title || extra) && (
        <div
          style={{
            padding: '10px 14px',
            borderBottom: afterSys.borderSoft,
            display: 'flex',
            justifyContent: 'space-between',
            gap: 8,
            alignItems: 'center',
            background: afterSys.fill,
          }}
        >
          <span style={{ fontSize: 13, fontWeight: 600, color: afterSys.text1 }}>{title}</span>
          {extra}
        </div>
      )}
      <div style={{ padding: 14 }}>{children}</div>
    </div>
  );
}

/** —— Unified entity list demos (工作台 / 智能体 / 知识库 / 工具 / 记忆 / 模型) —— */

type EntityListCardDemo = UnifiedOpsCardProps & { kind?: string };

interface EntityListModuleDemo {
  id: string;
  route: string;
  menuTitle: string;
  pageTitle: string;
  refs: string[];
  icon: string;
  listTitle: string;
  subtitle: string;
  totalLabel?: string;
  searchPlaceholder: string;
  defaultFilter?: string;
  actionByFilter?: Record<string, string>;
  filters: { key: string; label: string; count?: number }[];
  cards: EntityListCardDemo[];
}

export const OPS_ENTITY_LIST_MODULES = {
  studio: {
    id: 'studio',
    route: '/opspilot/studio',
    menuTitle: '工作台',
    pageTitle: '工作台 · 机器人列表',
    refs: ['Look B 统一卡', 'Pin + 状态 + tag + Owner/Team'],
    icon: 'jiqirenjiaohukapian',
    listTitle: '工作台',
    subtitle: '全模块统一 B 卡风格；内容字段各模块不同，卡片解剖一致',
    totalLabel: '4 bots',
    searchPlaceholder: '搜索名称、团队',
    filters: [
      { key: 'all', label: '全部', count: 4 },
      { key: 'pinned', label: '置顶', count: 2 },
      { key: 'online', label: 'Online', count: 3 },
    ],
    cards: [
      {
        name: 'Incident Copilot',
        description: '协调告警处置、审批跟进与变更回滚，覆盖生产值班主路径。',
        status: 'online',
        updatedAt: '12m 前',
        pinned: true,
        meta: ['Chatflow', 'gpt-4o'],
        team: 'SRE',
      },
      {
        name: 'Knowledge Desk',
        description: '面向运维手册与 Wiki 的问答助手，支持引用溯源与多知识库检索。',
        status: 'offline',
        updatedAt: '昨天',
        meta: ['Chatflow', 'RAG'],
        team: 'Knowledge',
      },
      {
        name: 'Runbook Flow',
        description: 'Chatflow 编排发布检查、通知与人工审批节点，串联变更到回滚闭环。',
        status: 'online',
        updatedAt: '3h 前',
        meta: ['Chatflow', '审批流'],
        team: ['Ops', 'Platform', 'SRE', 'NOC'],
      },
      {
        name: 'Patch Advisor',
        description: '补丁风险评估与分批发布建议，给出可回滚窗口与影响面摘要。',
        status: 'online',
        updatedAt: '1h 前',
        pinned: true,
        meta: ['Chatflow', '风险评估'],
        team: ['SRE', 'Security'],
      },
    ],
  },
  skill: {
    id: 'skill',
    route: '/opspilot/skill',
    menuTitle: '智能体',
    pageTitle: '智能体 · 列表',
    refs: ['Look B 统一卡'],
    icon: 'weibiaoti3',
    listTitle: '智能体',
    subtitle: '与选型 B 相同卡片；meta 填类型 + 模型名',
    totalLabel: '3 agents',
    searchPlaceholder: '搜索智能体',
    filters: [
      { key: 'all', label: '全部', count: 3 },
      { key: 'pinned', label: '置顶', count: 1 },
    ],
    cards: [
      {
        name: 'Kubernetes Diagnosis',
        description: '诊断工作负载配置风险，给出可回滚修复与审批卡。',
        status: 'online',
        updatedAt: '20m 前',
        pinned: true,
        meta: ['Q&A', 'gpt-4o'],
        team: 'Default',
      },
      {
        name: 'Runbook Q&A',
        description: '基于运维手册的检索问答，输出步骤与引用。',
        status: 'online',
        updatedAt: '昨天',
        meta: ['RAG', 'deepseek'],
        team: 'SRE',
      },
      {
        name: 'Incident Planner',
        description: '将告警收敛为变更计划，并触发人机确认。',
        status: 'offline',
        updatedAt: '3d 前',
        meta: ['Planner'],
        team: 'Platform',
      },
    ],
  },
  wiki: {
    id: 'wiki',
    route: '/opspilot/wiki',
    menuTitle: '知识库',
    pageTitle: '知识库 · 列表',
    refs: ['Look B 统一卡'],
    icon: 'zhishiku',
    listTitle: '知识库',
    subtitle: '同一 B 卡；无在线态时可省略 status 行',
    totalLabel: '3 knowledge bases',
    searchPlaceholder: '搜索知识库',
    filters: [{ key: 'all', label: '全部', count: 3 }],
    cards: [
      {
        name: 'SRE Playbooks',
        description: '生产故障、发布与回滚手册，含探针与变更窗口约定。',
        updatedAt: '1h 前',
        pinned: true,
        meta: ['Ready', '128 docs'],
        team: 'SRE',
      },
      {
        name: 'K8s Standards',
        description: '集群规范、探针清单与滚动发布检查项。',
        status: 'building',
        updatedAt: '刚刚',
        meta: ['Building'],
        team: 'Platform',
      },
      {
        name: 'Oncall Handbook',
        description: '值班交接、升级路径与常见告警处置。',
        updatedAt: '昨天',
        meta: ['Ready', '64 docs'],
        team: ['SRE', 'NOC', 'Platform'],
      },
    ],
  },
  tool: {
    id: 'tool',
    route: '/opspilot/tool',
    menuTitle: '工具',
    pageTitle: '工具 · 列表',
    refs: ['Look B 统一卡', '工具 / 技能 / MCP'],
    icon: 'gongju-',
    listTitle: '工具',
    subtitle: '与现网一致：工具、技能、MCP 三个分类',
    searchPlaceholder: '搜索名称或说明',
    defaultFilter: 'builtin',
    actionByFilter: {
      builtin: '',
      skills: '导入技能包',
      mcp: '添加',
    },
    filters: [
      { key: 'builtin', label: '工具' },
      { key: 'skills', label: '技能' },
      { key: 'mcp', label: 'MCP' },
    ],
    cards: [
      {
        kind: 'builtin',
        name: '监控',
        description: '用当前用户身份查已纳管对象、实例、指标时序与告警。',
        icon: 'gongjuji',
        footer: 'none',
        meta: [],
      },
      {
        kind: 'builtin',
        name: 'Redis',
        description: 'Redis 连接管理、键值查询与数据库诊断。',
        icon: 'gongjuji',
        footer: 'none',
        meta: [],
      },
      {
        kind: 'builtin',
        name: 'MySQL',
        description: 'MySQL 连接管理、结构查看、安全查询与性能诊断。',
        icon: 'gongjuji',
        footer: 'none',
        meta: [],
      },
      {
        kind: 'builtin',
        name: 'Kubernetes工具',
        description: 'Kubernetes 资源查询、故障诊断与配置分析。',
        icon: 'gongjuji',
        footer: 'none',
        meta: [],
      },
      {
        kind: 'builtin',
        name: '工作流附件文件',
        description: '为工作流执行生成 Markdown、PDF 或 Word 附件。',
        icon: 'gongjuji',
        footer: 'none',
        meta: [],
      },
      {
        kind: 'skills',
        name: 'K8s 变更诊断',
        description: '诊断工作负载配置风险，给出可回滚修复与审批卡。',
        icon: 'jinengpeixun',
        footer: 'none',
        meta: [],
      },
      {
        kind: 'skills',
        name: '值班手册',
        description: '值班交接、升级路径与常见告警处置。',
        icon: 'jinengpeixun',
        footer: 'none',
        meta: [],
      },
      {
        kind: 'mcp',
        name: 'k8s-ops',
        description: 'Kubernetes MCP：查询、diff、受控 patch。',
        footer: 'none',
        meta: ['运维'],
      },
      {
        kind: 'mcp',
        name: 'cmdb-query',
        description: 'CMDB 资源检索与拓扑只读查询。',
        footer: 'none',
        meta: ['通用'],
      },
      {
        kind: 'mcp',
        name: 'monitor-promql',
        description: 'Prometheus 查询与告警上下文。',
        footer: 'none',
        meta: ['运维'],
      },
    ],
  },
  memory: {
    id: 'memory',
    route: '/opspilot/memory',
    menuTitle: '记忆',
    pageTitle: '记忆 · 空间列表',
    refs: ['Look B 统一卡', 'Owner · Team footer'],
    icon: 'shujuguanli',
    listTitle: '记忆空间',
    subtitle: '同一 B 卡；footer 与其他列表一致：Owner · Team',
    searchPlaceholder: '搜索空间',
    filters: [{ key: 'all', label: '全部', count: 2 }],
    cards: [
      {
        name: 'Prod Ops Memory',
        description: '生产运维长期记忆：变更例外、探针约定与联系人。',
        updatedAt: '15m 前',
        meta: ['记忆条数: 128', '团队'],
        owner: 'admin',
        team: 'SRE',
        showPin: false,
      },
      {
        name: 'Change Window',
        description: '变更窗口与冻结期记录，供 Agent 写入前校验。',
        updatedAt: '昨天',
        meta: ['记忆条数: 24', '个人'],
        owner: 'alice',
        team: 'Platform',
        showPin: false,
      },
    ],
  },
  provider: {
    id: 'provider',
    route: '/opspilot/provider',
    menuTitle: '模型',
    pageTitle: '模型 · 供应商列表',
    refs: ['Look B 统一卡', 'footer:provider 模型数+开关'],
    icon: 'moxing2',
    listTitle: '模型供应商',
    subtitle: '同一 B 卡解剖；footer 为 N 个模型 + 开关（非 Owner/Team）',
    searchPlaceholder: '搜索供应商...',
    filters: [{ key: 'all', label: '全部', count: 5 }],
    cards: [
      {
        name: 'openCode',
        description: '\u00a0',
        vendorIcon: 'Default',
        meta: ['其他'],
        footer: 'provider',
        modelCount: 1,
        enabled: true,
        showPin: false,
      },
      {
        name: '111',
        description: '\u00a0',
        vendorIcon: 'Default',
        meta: ['其他'],
        footer: 'provider',
        modelCount: 1,
        enabled: true,
        showPin: false,
      },
      {
        name: 'miniMax',
        description: '\u00a0',
        vendorIcon: 'Default',
        meta: ['其他'],
        footer: 'provider',
        modelCount: 1,
        enabled: true,
        showPin: false,
      },
      {
        name: 'wwww',
        description: '\u00a0',
        vendorIcon: 'GPT',
        meta: ['OpenAI'],
        footer: 'provider',
        modelCount: 9,
        enabled: true,
        showPin: false,
      },
      {
        name: 'test',
        description: '11111',
        vendorIcon: 'GPT',
        meta: ['OpenAI'],
        footer: 'provider',
        modelCount: 1,
        enabled: true,
        showPin: false,
      },
    ],
  },
} satisfies Record<string, EntityListModuleDemo>;


function EntityListPageBody({
  module,
  filter,
  setFilter,
}: {
  module: EntityListModuleDemo;
  filter: string;
  setFilter: (key: string) => void;
}) {
  const visibleCards = module.cards.filter((card) => !card.kind || card.kind === filter);
  const primaryAction = module.actionByFilter?.[filter];

  return (
    <UnifiedListChrome
      title={module.listTitle}
      subtitle={module.subtitle}
      totalLabel={module.totalLabel}
      filters={module.filters}
      filterValue={filter}
      onFilterChange={setFilter}
      searchPlaceholder={module.searchPlaceholder}
      primaryAction={primaryAction === undefined ? '新建' : primaryAction}
    >
      {visibleCards.map((card) => {
        const { kind, ...cardProps } = card;
        return <UnifiedOpsCard key={`${kind ?? 'all'}-${card.name}`} {...cardProps} icon={card.icon ?? module.icon} />;
      })}
    </UnifiedListChrome>
  );
}

function EntityListModuleSection({ module }: { module: EntityListModuleDemo }) {
  const { filter, setFilter } = useListFilter(module.defaultFilter ?? 'all');
  return (
    <section style={{ display: 'grid', gap: 10 }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          gap: 10,
          flexWrap: 'wrap',
        }}
      >
        <span
          style={{
            fontSize: 13,
            fontWeight: 600,
            color: afterSys.text1,
            letterSpacing: '-0.01em',
          }}
        >
          {module.menuTitle}
        </span>
        <span style={{ fontSize: 11, color: afterSys.text4, fontFamily: afterSys.mono }}>{module.route}</span>
      </div>
      <EntityListPageBody module={module} filter={filter} setFilter={setFilter} />
    </section>
  );
}

/** 六模块实体列表对照板 — 一屏确认卡片统一性 */
export function PageUnifiedEntityLists() {
  const modules = [
    OPS_ENTITY_LIST_MODULES.studio,
    OPS_ENTITY_LIST_MODULES.skill,
    OPS_ENTITY_LIST_MODULES.wiki,
    OPS_ENTITY_LIST_MODULES.tool,
    OPS_ENTITY_LIST_MODULES.memory,
    OPS_ENTITY_LIST_MODULES.provider,
  ];
  return (
    <div
      style={{
        minHeight: '100vh',
        background: afterSys.page,
        padding: 16,
        display: 'grid',
        gap: 28,
      }}
    >
      <header
        style={{
          padding: 16,
          borderRadius: afterSys.radius,
          border: afterSys.border,
          background: afterSys.bg,
        }}
      >
        <Title level={4} style={{ margin: 0, color: afterSys.text1 }}>
          OpsPilot 实体列表 · 统一卡片系统
        </Title>
        <Paragraph style={{ margin: '8px 0 0', fontSize: 13, color: afterSys.text3, maxWidth: 760, lineHeight: 1.55 }}>
          全模块统一 <Text strong>选型 B</Text> 卡片（wash + 固定解剖）。各列表只换 meta / footer 等内容，不换卡片风格。
        </Paragraph>
      </header>
      {modules.map((m) => (
        <EntityListModuleSection key={m.id} module={m} />
      ))}
    </div>
  );
}

function EntityListPage({ moduleId }: { moduleId: keyof typeof OPS_ENTITY_LIST_MODULES }) {
  const listModule = OPS_ENTITY_LIST_MODULES[moduleId];
  const { filter, setFilter } = useListFilter(listModule.defaultFilter ?? 'all');
  return (
    <PageEffectFrame route={listModule.route} title={listModule.pageTitle} refs={listModule.refs}>
      <EntityListPageBody module={listModule} filter={filter} setFilter={setFilter} />
    </PageEffectFrame>
  );
}

/** —— Pages —— */

export function PageOpsilotRedirect() {
  return (
    <PageEffectFrame route="/opspilot" title="OpsPilot 入口" refs={['Linear 短路径', '空态下一步']}>
      <Panel>
        <div style={{ padding: '40px 16px' }}>
          <Empty description={<span>进入首个可用模块：<Text strong>Studio</Text></span>}>
            <Button type="primary">前往 Studio</Button>
          </Empty>
        </div>
      </Panel>
    </PageEffectFrame>
  );
}

export function PageStudioList() {
  return <EntityListPage moduleId="studio" />;
}

export function PageStudioDetailRedirect() {
  return (
    <PageEffectFrame route="/opspilot/studio/detail" title="Studio 详情入口" refs={['短路径空态']}>
      <Panel>
        <div style={{ padding: '32px 12px' }}>
          <Empty description="子页：设置 / 通道 / API / 统计 / 日志">
            <Button type="primary">打开设置</Button>
          </Empty>
        </div>
      </Panel>
    </PageEffectFrame>
  );
}

const STUDIO_NODE_LIBRARY = ['开始', 'LLM', '工具', '条件', '知识库', '结束'];

function StudioNodeChip({ label }: { label: string }) {
  return (
    <div
      style={{
        border: afterSys.border,
        borderRadius: 8,
        padding: '8px 10px',
        fontSize: 11,
        color: afterSys.text2,
        background: afterSys.bg,
      }}
    >
      {label}
    </div>
  );
}

function StudioCanvasSchematic() {
  const nodes = [
    { id: 'start', label: '开始', x: 48, y: 72 },
    { id: 'llm', label: 'LLM · gpt-4o', x: 220, y: 56 },
    { id: 'tool', label: '工具 · 变更审批', x: 392, y: 72 },
    { id: 'end', label: '结束', x: 564, y: 72 },
  ];

  return (
    <div
      style={{
        position: 'relative',
        minHeight: 280,
        borderRadius: afterSys.radius,
        border: afterSys.border,
        background: `repeating-linear-gradient(
          0deg,
          transparent,
          transparent 23px,
          var(--color-border-1) 23px,
          var(--color-border-1) 24px
        ),
        repeating-linear-gradient(
          90deg,
          transparent,
          transparent 23px,
          var(--color-border-1) 23px,
          var(--color-border-1) 24px
        )`,
        backgroundColor: afterSys.bg,
        overflow: 'hidden',
      }}
    >
      <svg
        aria-hidden
        style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}
      >
        <path
          d="M 132 96 H 220 M 348 96 H 392 M 520 96 H 564"
          stroke="var(--color-primary)"
          strokeWidth="2"
          fill="none"
          opacity={0.45}
        />
      </svg>
      {nodes.map((node) => (
        <div
          key={node.id}
          style={{
            position: 'absolute',
            left: node.x,
            top: node.y,
            minWidth: 112,
            padding: '10px 12px',
            borderRadius: 10,
            border: afterSys.border,
            background: afterSys.fill,
            boxShadow: '0 1px 2px rgba(0,0,0,0.04)',
            fontSize: 12,
            fontWeight: 600,
            color: afterSys.text1,
          }}
        >
          {node.label}
        </div>
      ))}
    </div>
  );
}

export function PageStudioSettings() {
  const saveMenu = (
    <Menu style={{ width: 260 }}>
      <Menu.Item key="tip" disabled style={{ whiteSpace: 'normal', opacity: 1, cursor: 'default' }}>
        <Text type="secondary" style={{ fontSize: 12 }}>
          保存并发布会同步画布与基本信息，发布后应用在线可用。
        </Text>
      </Menu.Item>
      <Menu.Divider />
      <Menu.Item key="save_publish">
        <Button type="primary" size="small" block>
          保存并发布
        </Button>
      </Menu.Item>
      <Menu.Item key="save_only">
        <Button size="small" block>
          仅保存
        </Button>
      </Menu.Item>
    </Menu>
  );

  return (
    <PageEffectFrame
      route="/opspilot/studio/detail/settings"
      title="Studio 设置 / Chatflow"
      refs={['左栏二级：设置/通道/日志/统计/接口', '无顶部模块说明条']}
    >
      <AfterEntityShell name="Incident Copilot" items={STUDIO_NAV} active="settings">
      <div style={{ position: 'relative', minHeight: 460 }}>
        <div
          style={{
            position: 'absolute',
            top: 0,
            right: 0,
            zIndex: 1,
            display: 'flex',
            gap: 8,
            alignItems: 'center',
          }}
        >
          <span
            style={{
              fontSize: 11,
              color: afterSys.warning,
              display: 'inline-flex',
              gap: 5,
              alignItems: 'center',
              marginRight: 4,
            }}
          >
            <span style={{ width: 6, height: 6, borderRadius: 999, background: afterSys.warning }} />
            未保存
          </span>
          <Tag color="green" style={{ margin: 0 }}>
            Online
          </Tag>
          <Dropdown overlay={saveMenu} trigger={['click']}>
            <Button type="primary" size="small" icon={<DownOutlined />}>
              保存
            </Button>
          </Dropdown>
        </div>

        <div style={{ display: 'flex', gap: 14, minHeight: 460, paddingTop: 36, alignItems: 'stretch' }}>
          <div
            style={{
              flex: '0 0 288px',
              borderRight: afterSys.divider,
              paddingRight: 12,
              minWidth: 0,
            }}
          >
            <Collapse
              ghost
              size="small"
              defaultActiveKey={['nodes']}
              expandIcon={({ isActive }) => <CaretRightOutlined rotate={isActive ? 90 : 0} />}
            >
              <Collapse.Panel key="information" header={<span style={{ fontSize: 13, fontWeight: 600 }}>基本信息</span>}>
                <Form layout="vertical" size="small" style={{ paddingTop: 4 }}>
                  <Form.Item label="名称" required style={{ marginBottom: 10 }}>
                    <Input defaultValue="Incident Copilot" />
                  </Form.Item>
                  <Form.Item label="管理组织" required style={{ marginBottom: 10 }}>
                    <Select defaultValue="SRE" options={[{ value: 'SRE', label: 'SRE' }]} />
                  </Form.Item>
                  <Form.Item label="使用组织" required style={{ marginBottom: 10 }}>
                    <Select
                      mode="multiple"
                      defaultValue={['SRE', 'NOC']}
                      options={[
                        { value: 'SRE', label: 'SRE' },
                        { value: 'NOC', label: 'NOC' },
                      ]}
                    />
                  </Form.Item>
                  <Form.Item label="简介" required style={{ marginBottom: 0 }}>
                    <Input.TextArea
                      rows={3}
                      defaultValue="协调告警处置、审批跟进与变更回滚，覆盖生产值班主路径。"
                    />
                  </Form.Item>
                </Form>
              </Collapse.Panel>
              <Collapse.Panel key="nodes" header={<span style={{ fontSize: 13, fontWeight: 600 }}>节点</span>}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, paddingTop: 4 }}>
                  {STUDIO_NODE_LIBRARY.map((label) => (
                    <StudioNodeChip key={label} label={label} />
                  ))}
                </div>
              </Collapse.Panel>
            </Collapse>
          </div>

          <div style={{ flex: 1, minWidth: 0, display: 'grid', gap: 10, alignContent: 'start' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
              <span style={{ fontSize: 13, fontWeight: 600, color: afterSys.text1 }}>画布</span>
              <Button size="small" type="text" danger>
                清空画布
              </Button>
            </div>
            <StudioCanvasSchematic />
          </div>

          <div style={{ flex: '0 0 300px', display: 'grid', gap: 12, alignContent: 'start' }}>
            <TaskRowsPolished />
          </div>
        </div>
      </div>
      </AfterEntityShell>
    </PageEffectFrame>
  );
}

export function PageStudioChannel() {
  return (
    <PageEffectFrame route="/opspilot/studio/detail/channel" title="通道配置" refs={['左栏二级，无顶部模块说明条']}>
      <AfterEntityShell name="Incident Copilot" items={STUDIO_NAV} active="channel">
      <Row gutter={[12, 12]}>
        {[
          { name: '企业微信', on: true, desc: '群机器人回调与应用凭证', updated: 'synced 2h' },
          { name: '钉钉', on: false, desc: '企业内部应用与 Stream 模式', updated: 'never' },
          { name: '飞书', on: true, desc: '事件订阅与消息卡片', updated: 'synced 40m' },
        ].map((c) => (
          <Col key={c.name} xs={24} md={8}>
            <div style={{ border: afterSys.border, borderRadius: afterSys.radius, background: afterSys.bg, padding: 14, height: '100%' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, marginBottom: 8 }}>
                <Text strong style={{ fontSize: 13 }}>{c.name}</Text>
                <StatusQuiet label={c.on ? '已启用' : '未启用'} tone={c.on ? 'ok' : 'mute'} />
              </div>
              <Paragraph style={{ fontSize: 12, color: afterSys.text3, minHeight: 40, marginBottom: 10 }}>{c.desc}</Paragraph>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Space size={8}>
                  <Switch size="small" checked={c.on} />
                  <Button type="link" size="small" style={{ padding: 0 }}>配置</Button>
                </Space>
                <span style={{ fontSize: 11, color: afterSys.text4, fontFamily: afterSys.mono }}>{c.updated}</span>
              </div>
            </div>
          </Col>
        ))}
      </Row>
      </AfterEntityShell>
    </PageEffectFrame>
  );
}

export function PageStudioApi() {
  return (
    <PageEffectFrame route="/opspilot/studio/detail/api" title="API 文档" refs={['左栏二级，无顶部模块说明条']}>
      <AfterEntityShell name="Incident Copilot" items={STUDIO_NAV} active="api">
      <Panel
        title="Chat Completion"
        extra={<Button size="small">复制</Button>}
      >
        <Paragraph type="secondary" style={{ fontSize: 12, marginTop: 0 }}>
          POST /api/proxy/opspilot/bot_mgmt/chat/
        </Paragraph>
        <pre
          style={{
            margin: 0,
            padding: 12,
            background: afterSys.fill,
            border: afterSys.borderSoft,
            borderRadius: afterSys.radiusSm,
            fontSize: 12,
            overflow: 'auto',
            fontFamily: afterSys.mono,
            color: afterSys.text2,
            lineHeight: 1.55,
          }}
        >
          {`curl -X POST "$HOST/api/proxy/opspilot/bot_mgmt/chat/" \\\n  -H "Authorization: Bearer <token>" \\\n  -d '{"bot_id": 201, "message": "hello"}'`}
        </pre>
      </Panel>
      </AfterEntityShell>
    </PageEffectFrame>
  );
}

export function PageStudioStatistics() {
  return (
    <PageEffectFrame route="/opspilot/studio/detail/statistics" title="用量统计" refs={['左栏二级，无顶部模块说明条']}>
      <AfterEntityShell name="Incident Copilot" items={STUDIO_NAV} active="statistics">
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
        <Segmented options={['近 24h', '近 7 天', '近 30 天']} defaultValue="近 7 天" size="small" />
      </div>
      <BeautifulInsightStrip
        items={[
          { label: '会话数', value: '1,284', hint: '含 Chatflow', delta: '+8.2%' },
          { label: 'Token', value: '3.2M', hint: '输入 + 输出', delta: '+3.1%' },
          { label: '成功率', value: '98.4%', hint: '终态成功', delta: '+0.4%', tone: 'ok' },
          { label: 'P95 延迟', value: '1.8s', hint: '端到端', delta: '-120ms', tone: 'ok' },
        ]}
      />
      <div
        style={{
          marginTop: 12,
          border: afterSys.border,
          borderRadius: afterSys.radius,
          height: 200,
          display: 'grid',
          placeItems: 'center',
          background: afterSys.bg,
        }}
      >
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 13, color: afterSys.text2 }}>趋势示意</div>
          <div style={{ fontSize: 11, color: afterSys.text4, marginTop: 4 }}>克制工作台 · 非大屏炫光</div>
        </div>
      </div>
      </AfterEntityShell>
    </PageEffectFrame>
  );
}

export function PageStudioLogInfo() {
  const { filter, setFilter } = useListFilter('all');
  return (
    <PageEffectFrame route="/opspilot/studio/detail/logInfo" title="日志" refs={['左栏二级，无顶部模块说明条']}>
      <AfterEntityShell name="Incident Copilot" items={STUDIO_NAV} active="logs">
      <div style={{ display: 'grid', gap: afterSys.gap }}>
        <div style={{ border: afterSys.border, borderRadius: afterSys.radius, overflow: 'hidden', background: afterSys.bg }}>
          <div style={{ padding: '12px 14px', borderBottom: afterSys.borderSoft, display: 'flex', justifyContent: 'space-between', gap: 12 }}>
            <div>
              <div style={{ fontSize: 15, fontWeight: 600, color: afterSys.text1 }}>会话 / 工作流日志</div>
              <div style={{ marginTop: 4, fontSize: 12, color: afterSys.text3 }}>与列表页同一筛选语言</div>
            </div>
            <Button type="primary" size="middle">导出</Button>
          </div>
          <div style={{ padding: '10px 14px', background: afterSys.fill, display: 'flex', flexWrap: 'wrap', gap: 10, justifyContent: 'space-between' }}>
            <UnifiedFilterChips
              options={[
                { key: 'all', label: '全部', count: 128 },
                { key: 'ok', label: '成功', count: 110 },
                { key: 'fail', label: '失败', count: 12 },
                { key: 'run', label: '运行中', count: 6 },
              ]}
              value={filter}
              onChange={setFilter}
            />
            <Input.Search allowClear placeholder="execution_id / 用户" style={{ width: 248 }} />
          </div>
        </div>
        <div style={{ border: afterSys.border, borderRadius: afterSys.radius, overflow: 'hidden', background: afterSys.bg }}>
          <Table
            size="middle"
            pagination={{ pageSize: 6, showTotal: (t) => `共 ${t} 条` }}
            dataSource={[
              { key: 1, id: 'exec-1024', user: 'alice', type: 'Chat', status: '成功', time: '14:02:11', lat: '1.2s' },
              { key: 2, id: 'exec-1025', user: 'bob', type: 'Chatflow', status: '失败', time: '14:05:03', lat: '4.8s' },
              { key: 3, id: 'exec-1026', user: 'carol', type: 'Chat', status: '运行中', time: '14:08:40', lat: '…' },
            ]}
            columns={[
              {
                title: 'Execution',
                dataIndex: 'id',
                render: (v: string) => <span style={{ fontFamily: afterSys.mono, fontSize: 12 }}>{v}</span>,
              },
              { title: '类型', dataIndex: 'type' },
              { title: '用户', dataIndex: 'user' },
              {
                title: '状态',
                dataIndex: 'status',
                render: (v: string) => (
                  <StatusQuiet label={v} tone={v === '成功' ? 'ok' : v === '失败' ? 'bad' : 'run'} />
                ),
              },
              {
                title: '延迟',
                dataIndex: 'lat',
                render: (v: string) => <span style={{ fontFamily: afterSys.mono, fontSize: 12, color: afterSys.text3 }}>{v}</span>,
              },
              { title: '时间', dataIndex: 'time' },
              {
                title: '操作',
                render: () => (
                  <Space>
                    <Button type="link" size="small">详情</Button>
                    <Button type="link" size="small">回放</Button>
                  </Space>
                ),
              },
            ]}
          />
        </div>
      </div>
      </AfterEntityShell>
    </PageEffectFrame>
  );
}

export function PageStudioChat() {
  return (
    <PageEffectFrame
      route="/opspilot/studio/chat"
      title="Studio 聊天工作台"
      refs={['可切换应用', '无头像气泡', 'Thought / Tools 分层']}
    >
      <OpsPilotChatWorkspace />
    </PageEffectFrame>
  );
}

export function PageSkillList() {
  return <EntityListPage moduleId="skill" />;
}

export function PageSkillDetailRedirect() {
  return (
    <PageEffectFrame route="/opspilot/skill/detail" title="Skill 详情入口" refs={['短路径空态']}>
      <Panel>
        <div style={{ padding: '32px 12px' }}>
          <Empty description="子页：设置 / 规则">
            <Button type="primary">打开设置</Button>
          </Empty>
        </div>
      </Panel>
    </PageEffectFrame>
  );
}

export function PageSkillSettings() {
  return (
    <PageEffectFrame
      route="/opspilot/skill/detail/settings"
      title="Skill 设置"
      refs={['一张工作台：菜单与内容同面']}
    >
      <AfterEntityShell name="K8s 变更诊断" items={SKILL_NAV} active="settings">
        <SkillSettingsWorkbench />
      </AfterEntityShell>
    </PageEffectFrame>
  );
}

export function PageSkillRules() {
  return (
    <PageEffectFrame route="/opspilot/skill/detail/channel" title="Skill 发布" refs={['左栏二级：设置 / 发布']}>
      <AfterEntityShell name="K8s 变更诊断" items={SKILL_NAV} active="publish">
      <Table
        size="middle"
        pagination={false}
        dataSource={[
          { key: 1, name: '夜间自动汇总', cron: '0 9 * * *', status: '启用' },
          { key: 2, name: '高危变更复核', cron: '事件触发', status: '停用' },
          { key: 3, name: '探针缺失巡检', cron: '0 */6 * * *', status: '启用' },
        ]}
        columns={[
          { title: '名称', dataIndex: 'name' },
          { title: '触发', dataIndex: 'cron', render: (v: string) => <span style={{ fontFamily: afterSys.mono, fontSize: 12 }}>{v}</span> },
          { title: '状态', dataIndex: 'status', render: (v: string) => <StatusQuiet label={v} tone={v === '启用' ? 'ok' : 'mute'} /> },
          { title: '操作', render: () => <Space><Button type="link" size="small">编辑</Button><Button type="link" size="small" danger>删除</Button></Space> },
        ]}
      />
      </AfterEntityShell>
    </PageEffectFrame>
  );
}

export function PageWikiList() {
  return <EntityListPage moduleId="wiki" />;
}

export function PageWikiDetail() {
  return (
    <PageEffectFrame route="/opspilot/wiki/detail" title="Wiki 工作区" refs={['左栏二级：概览/素材/知识/构建/检查/设置', '无顶部模块说明条']}>
      <AfterEntityShell name="SRE Playbooks" items={WIKI_NAV} active="knowledge">
      <div className="flex min-h-[520px]">
        <div className="w-[220px] shrink-0 border-r border-[var(--color-fill-2)] p-2.5">
          <Input.Search size="small" placeholder="筛选目录" style={{ marginBottom: 8 }} />
          <Tree defaultExpandAll defaultSelectedKeys={['0-0']} treeData={[{ title: 'SRE', key: '0', children: [{ title: '探针清单', key: '0-0' }, { title: '发布回滚', key: '0-1' }] }]} />
        </div>
        <div className="min-w-0 flex-[1.05] border-r border-[var(--color-fill-2)] p-4">
          <div className="mb-2.5 flex items-start justify-between gap-2">
            <div>
              <Title level={5} style={{ margin: 0 }}>探针清单</Title>
              <div className="mt-1 font-[ui-monospace,SFMono-Regular,Menlo,monospace] text-[11px] text-[var(--color-text-4)]">doc · kb-01/probes</div>
            </div>
            <Space><Button size="small">编辑</Button><Button size="small" type="primary">发布</Button></Space>
          </div>
          <Paragraph style={{ fontSize: 13, lineHeight: 1.65 }}>新工作负载上线前必须配置 readiness/liveness，并在预发验证滚动发布。</Paragraph>
          <Paragraph type="secondary" style={{ fontSize: 12 }}>相关：nginx-web、api-gateway 已在检查队列标为高优先级。</Paragraph>
        </div>
        <div className="min-w-0 flex-1 overflow-auto p-2.5">
          <div className="mb-2 font-[ui-monospace,SFMono-Regular,Menlo,monospace] text-[11px] text-[var(--color-text-4)]">assistant · check decisions</div>
          <OpsPilotConversationDemo />
        </div>
      </div>
      </AfterEntityShell>
    </PageEffectFrame>
  );
}

export function PageToolList() {
  return <EntityListPage moduleId="tool" />;
}

export function PageProviderList() {
  return <EntityListPage moduleId="provider" />;
}

export function PageProviderDetail() {
  return (
    <PageEffectFrame route="/opspilot/provider/detail" title="供应商详情" refs={['页内 Tabs，无左侧二级菜单']}>
      <ProviderDetailWorkbench />
    </PageEffectFrame>
  );
}

export function PageMemoryList() {
  return <EntityListPage moduleId="memory" />;
}

export function PageMemoryMemories() {
  return (
    <PageEffectFrame route="/opspilot/memory/detail/memories" title="记忆" refs={['左栏二级：配置 / 记忆', '无顶部模块说明条']}>
      <AfterEntityShell name="Prod Ops Memory" items={MEMORY_NAV} active="memories">
        <MemoryMemoriesWorkbench />
      </AfterEntityShell>
    </PageEffectFrame>
  );
}

export function PageMemoryConfig() {
  return (
    <PageEffectFrame route="/opspilot/memory/detail/config" title="记忆配置" refs={['左栏二级：配置 / 记忆']}>
      <AfterEntityShell name="Prod Ops Memory" items={MEMORY_NAV} active="config">
        <MemoryConfigWorkbench />
      </AfterEntityShell>
    </PageEffectFrame>
  );
}

export function PageSettingsRedirect() {
  return (
    <PageEffectFrame route="/opspilot/settings" title="设置" refs={['入口跳转到我的配额']}>
      <SettingsQuotaWorkbench />
    </PageEffectFrame>
  );
}

export function PageSettingsQuota() {
  return (
    <PageEffectFrame route="/opspilot/settings/quota" title="我的配额" refs={['智能体 / 机器人用量']}>
      <SettingsQuotaWorkbench />
    </PageEffectFrame>
  );
}

export function PageSettingsManage() {
  return (
    <PageEffectFrame route="/opspilot/settings/manage" title="管理配额" refs={['名称 / 智能体 / 机器人']}>
      <SettingsManageWorkbench />
    </PageEffectFrame>
  );
}

export const ALL_PAGE_EFFECTS: { id: string; label: string; render: () => ReactNode }[] = [
  { id: 'unified-lists', label: '00 六模块统一列表', render: () => <PageUnifiedEntityLists /> },
  { id: 'opspilot', label: '01 入口重定向', render: () => <PageOpsilotRedirect /> },
  { id: 'studio', label: '02 工作台列表', render: () => <PageStudioList /> },
  { id: 'studio-detail', label: '03 Studio 详情入口', render: () => <PageStudioDetailRedirect /> },
  { id: 'studio-settings', label: '04 Studio 设置', render: () => <PageStudioSettings /> },
  { id: 'studio-channel', label: '05 Studio 通道', render: () => <PageStudioChannel /> },
  { id: 'studio-api', label: '06 Studio API', render: () => <PageStudioApi /> },
  { id: 'studio-statistics', label: '07 Studio 统计', render: () => <PageStudioStatistics /> },
  { id: 'studio-log', label: '08 Studio 日志', render: () => <PageStudioLogInfo /> },
  { id: 'studio-chat', label: '09 Studio 聊天', render: () => <PageStudioChat /> },
  { id: 'skill', label: '10 智能体列表', render: () => <PageSkillList /> },
  { id: 'skill-detail', label: '11 Skill 详情入口', render: () => <PageSkillDetailRedirect /> },
  { id: 'skill-settings', label: '12 Skill 设置', render: () => <PageSkillSettings /> },
  { id: 'skill-rules', label: '13 Skill 规则', render: () => <PageSkillRules /> },
  { id: 'wiki', label: '14 知识库列表', render: () => <PageWikiList /> },
  { id: 'wiki-detail', label: '15 Wiki 详情', render: () => <PageWikiDetail /> },
  { id: 'tool', label: '16 工具列表', render: () => <PageToolList /> },
  { id: 'provider', label: '17 模型列表', render: () => <PageProviderList /> },
  { id: 'provider-detail', label: '18 供应商详情', render: () => <PageProviderDetail /> },
  { id: 'memory', label: '19 记忆列表', render: () => <PageMemoryList /> },
  { id: 'memory-memories', label: '20 记忆', render: () => <PageMemoryMemories /> },
  { id: 'memory-config', label: '21 记忆配置', render: () => <PageMemoryConfig /> },
  { id: 'settings', label: '22 设置入口', render: () => <PageSettingsRedirect /> },
  { id: 'settings-quota', label: '23 我的配额', render: () => <PageSettingsQuota /> },
  { id: 'settings-manage', label: '24 管理配额', render: () => <PageSettingsManage /> },
];
