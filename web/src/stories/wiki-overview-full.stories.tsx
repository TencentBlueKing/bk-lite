'use client';

import { useState } from 'react';
import type { Meta, StoryObj } from '@storybook/nextjs';
import { RobotOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { Button, Empty, Input, Space, Spin, Tag } from 'antd';

// 整体效果稿:左 = 基础信息(资料/关系/待审核 + 处理异常 + 最近知识/构建 + 风险/智能体)
//         右 = 常驻对话面板(空/对话/加载/错误 4 态)
// 4 套基础信息数据 × 4 套右栏态 = 8 个组合 story

interface ProcessingIssue {
  status: 'pending' | 'parsing' | 'building' | 'built' | 'failed' | 'updated' | 'invalid';
  count: number;
}

interface BaseInfo {
  materialCount: number;
  pageCount: number;
  relationCount: number;
  pendingReviewCount: number;
  processing: ProcessingIssue[];
  recentPages: Array<{ id: string; title: string; type: string; status: string }>;
  recentBuilds: Array<{ id: string; trigger: string; status: string; time: string }>;
  risks: Array<{ id: string; type: string; title: string }>;
  agents: Array<{ id: string; name: string }>;
}

const PROC_LABEL: Record<ProcessingIssue['status'], { color: string; text: string }> = {
  pending: { color: 'default', text: '待解析' },
  parsing: { color: 'processing', text: '解析中' },
  building: { color: 'processing', text: '构建中' },
  built: { color: 'green', text: '已构建' },
  failed: { color: 'red', text: '失败' },
  updated: { color: 'blue', text: '待更新' },
  invalid: { color: 'red', text: '失效' },
};

const StatusMeta: Record<string, { color: string; text: string }> = {
  built: { color: 'green', text: '已构建' },
  success: { color: 'green', text: '成功' },
  partial: { color: 'orange', text: '部分成功' },
  source_updated: { color: 'blue', text: '待更新' },
};

// ── 4 套基础信息变体 ──
const DEFAULT_INFO: BaseInfo = {
  materialCount: 42,
  pageCount: 18,
  relationCount: 87,
  pendingReviewCount: 3,
  processing: [
    { status: 'built', count: 2 },
    { status: 'parsing', count: 1 },
    { status: 'failed', count: 1 },
  ],
  recentPages: [
    { id: 'p1', title: 'CMDB 资产录入流程', type: 'procedure', status: 'built' },
    { id: 'p2', title: '告警处理 SOP', type: 'sop', status: 'built' },
    { id: 'p3', title: 'Kubernetes 部署规范', type: 'standard', status: 'source_updated' },
    { id: 'p4', title: '告警分页策略', type: 'standard', status: 'built' },
    { id: 'p5', title: '巡检作业指导书', type: 'sop', status: 'built' },
  ],
  recentBuilds: [
    { id: 'b1', trigger: 'material_update', status: 'success', time: '10 分钟前' },
    { id: 'b2', trigger: 'rebuild', status: 'success', time: '1 小时前' },
    { id: 'b3', trigger: 'material', status: 'partial', time: '昨天' },
    { id: 'b4', trigger: 'rebuild', status: 'success', time: '2 天前' },
    { id: 'b5', trigger: 'material_update', status: 'failed', time: '3 天前' },
  ],
  risks: [
    { id: 'r1', type: '失效关系', title: 'MySQL 安装文档 → 已归档页面' },
    { id: 'r2', type: 'Schema 变更', title: 'CMDB 知识页内容与新 Schema 不一致' },
  ],
  agents: [
    { id: 'a1', name: '运维助手' },
    { id: 'a2', name: '故障排查 Agent' },
  ],
};

const EMPTY_INFO: BaseInfo = {
  materialCount: 0,
  pageCount: 0,
  relationCount: 0,
  pendingReviewCount: 0,
  processing: [],
  recentPages: [],
  recentBuilds: [],
  risks: [],
  agents: [],
};

const LOW_COVERAGE_INFO: BaseInfo = {
  materialCount: 8,
  pageCount: 5,
  relationCount: 12,
  pendingReviewCount: 5,
  processing: [
    { status: 'pending', count: 2 },
    { status: 'parsing', count: 1 },
    { status: 'building', count: 1 },
    { status: 'failed', count: 2 },
    { status: 'invalid', count: 1 },
  ],
  recentPages: [
    { id: 'p1', title: 'CMDB 资产录入流程', type: 'procedure', status: 'built' },
    { id: 'p2', title: '告警处理 SOP', type: 'sop', status: 'source_updated' },
  ],
  recentBuilds: [
    { id: 'b1', trigger: 'material_update', status: 'failed', time: '5 分钟前' },
    { id: 'b2', trigger: 'rebuild', status: 'partial', time: '1 小时前' },
    { id: 'b3', trigger: 'material', status: 'failed', time: '3 小时前' },
  ],
  risks: [
    { id: 'r1', type: '失效关系', title: '3 条关系指向已删除的资料' },
    { id: 'r2', type: 'Schema 变更', title: 'CMDB 知识页内容与新 Schema 不一致' },
    { id: 'r3', type: '来源失效', title: '外链 https://example.com/wiki 已 404' },
  ],
  agents: [{ id: 'a1', name: '运维助手' }],
};

const LOTS_INFO: BaseInfo = {
  materialCount: 142,
  pageCount: 89,
  relationCount: 326,
  pendingReviewCount: 0,
  processing: [
    { status: 'built', count: 120 },
    { status: 'building', count: 4 },
    { status: 'parsing', count: 2 },
  ],
  recentPages: [
    { id: 'p1', title: 'K8s 节点扩容标准操作', type: 'procedure', status: 'built' },
    { id: 'p2', title: 'MySQL 慢查询处理流程', type: 'sop', status: 'built' },
    { id: 'p3', title: 'CMDB 资产录入流程', type: 'procedure', status: 'built' },
    { id: 'p4', title: 'Nginx 502 排查 SOP', type: 'sop', status: 'built' },
    { id: 'p5', title: 'PaaS 部署规范 v2', type: 'standard', status: 'built' },
  ],
  recentBuilds: [
    { id: 'b1', trigger: 'material_update', status: 'success', time: '10 分钟前' },
    { id: 'b2', trigger: 'rebuild', status: 'success', time: '25 分钟前' },
    { id: 'b3', trigger: 'material', status: 'success', time: '1 小时前' },
    { id: 'b4', trigger: 'rebuild', status: 'success', time: '2 小时前' },
    { id: 'b5', trigger: 'material_update', status: 'success', time: '3 小时前' },
  ],
  risks: [],
  agents: [
    { id: 'a1', name: '运维助手' },
    { id: 'a2', name: '故障排查 Agent' },
    { id: 'a3', name: '变更助手' },
    { id: 'a4', name: '新人 Onboarding 助手' },
  ],
};

// ── 左主内容:基础信息(纯内联,参考旧原型视觉) ──
const BaseInfoPanel: React.FC<{ info: BaseInfo }> = ({ info }) => (
  <div className="flex-1 space-y-4 overflow-y-auto pr-1">
    {/* 摘要 4 卡片:资料 / 知识 / 关系 / 待审核 */}
    <div className="grid grid-cols-4 gap-3">
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <div className="text-xs text-[var(--color-text-3)]">资料总数</div>
        <div className="mt-1 text-2xl font-semibold">{info.materialCount}</div>
      </div>
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <div className="text-xs text-[var(--color-text-3)]">知识数</div>
        <div className="mt-1 text-2xl font-semibold">{info.pageCount}</div>
      </div>
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <div className="text-xs text-[var(--color-text-3)]">关系数</div>
        <div className="mt-1 text-2xl font-semibold">{info.relationCount}</div>
      </div>
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <div className="text-xs text-[var(--color-text-3)]">待审核数</div>
        <div
          className={`mt-1 text-2xl font-semibold ${
            info.pendingReviewCount > 0 ? 'text-[var(--color-fail)]' : ''
          }`}
        >
          {info.pendingReviewCount}
        </div>
      </div>
    </div>

    {/* 处理与异常 */}
    <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold">处理与异常</h3>
        {info.processing.length === 0 && (
          <span className="text-xs text-[var(--color-text-3)]">--</span>
        )}
      </div>
      <Space wrap size={[8, 8]}>
        {info.processing.map((p) => (
          <Tag key={p.status} color={PROC_LABEL[p.status].color} className="m-0">
            {PROC_LABEL[p.status].text}: {p.count}
          </Tag>
        ))}
      </Space>
    </section>

    {/* 最近知识 + 构建 并排 */}
    <div className="grid grid-cols-2 gap-4">
      <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold">最近知识</h3>
          <Button type="link" size="small" className="text-xs">
            更多 →
          </Button>
        </div>
        <ul className="min-h-[148px] space-y-2">
          {info.recentPages.slice(0, 5).map((p) => (
            <li key={p.id} className="flex h-6 items-center justify-between text-xs">
              <span className="truncate">{p.title}</span>
              <Tag color={StatusMeta[p.status]?.color} className="m-0">
                {StatusMeta[p.status]?.text || p.status}
              </Tag>
            </li>
          ))}
          {Array.from({ length: Math.max(0, 5 - info.recentPages.length) }).map((_, i) => (
            <li
              key={`pad-p-${i}`}
              className="flex h-6 items-center text-xs text-transparent"
              aria-hidden="true"
            >
              .
            </li>
          ))}
          {info.recentPages.length === 0 && (
            <li>
              <Empty description="暂无知识" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            </li>
          )}
        </ul>
      </section>
      <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold">最近构建</h3>
          <Button type="link" size="small" className="text-xs">
            更多 →
          </Button>
        </div>
        <ul className="min-h-[148px] space-y-2">
          {info.recentBuilds.slice(0, 5).map((b) => (
            <li key={b.id} className="flex h-6 items-center justify-between text-xs">
              <span className="flex items-center gap-2">
                <Tag color="blue">{b.trigger}</Tag>
                <span className="text-[var(--color-text-3)]">{b.time}</span>
              </span>
              <Tag color={StatusMeta[b.status]?.color} className="m-0">
                {StatusMeta[b.status]?.text || b.status}
              </Tag>
            </li>
          ))}
          {Array.from({ length: Math.max(0, 5 - info.recentBuilds.length) }).map((_, i) => (
            <li
              key={`pad-b-${i}`}
              className="flex h-6 items-center text-xs text-transparent"
              aria-hidden="true"
            >
              .
            </li>
          ))}
          {info.recentBuilds.length === 0 && (
            <li>
              <Empty description="暂无构建" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            </li>
          )}
        </ul>
      </section>
    </div>

    {/* 风险 + 智能体 */}
    <div className="grid grid-cols-2 gap-4">
      <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <h3 className="mb-3 text-sm font-semibold">风险</h3>
        {info.risks.length === 0 ? (
          <span className="text-xs text-[var(--color-text-3)]">暂无风险</span>
        ) : (
          <ul className="space-y-2">
            {info.risks.map((r) => (
              <li key={r.id} className="flex items-center justify-between text-xs">
                <span>
                  <Tag color="orange">{r.type}</Tag>
                  <span className="ml-2">{r.title}</span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <h3 className="mb-3 text-sm font-semibold">使用的智能体</h3>
        {info.agents.length === 0 ? (
          <span className="text-xs text-[var(--color-text-3)]">暂无智能体使用</span>
        ) : (
          <Space wrap>
            {info.agents.map((a) => (
              <Tag key={a.id} icon={<RobotOutlined />} color="blue">
                {a.name}
              </Tag>
            ))}
          </Space>
        )}
      </section>
    </div>
  </div>
);

// ── 右栏:对话面板(4 态) ──
const SAMPLE_MSGS = [
  { id: 'm1', role: 'user' as const, content: 'CMDB 资产录入流程的当前版本是哪个?' },
  {
    id: 'm2',
    role: 'assistant' as const,
    content:
      '当前版本是 v3(2026-07-10 构建),基于「运维标准 v2026.06」和「CMDB 数据规范」两份资料生成。',
    sources: [
      { title: 'CMDB 资产录入流程', snippet: '## 流程概述\n1. 资产申请\n2. 审批\n3. 录入...' },
      { title: '运维标准 v2026.06', snippet: '### 资产分类\n按业务影响分 A/B/C 三级...' },
    ],
  },
  { id: 'm3', role: 'user' as const, content: '能不能加一步「合规校验」?' },
  {
    id: 'm4',
    role: 'assistant' as const,
    content: '可以,建议在第 3 步前插入「合规校验」环节,自动检查 IP/账号是否在合规列表。',
  },
];

const SUGGESTED = [
  '解释最近一次失败的构建',
  '有哪些页面需要重新构建?',
  '知识库的来源覆盖率多少?',
];

const RightPanel: React.FC<{
  variant: 'empty' | 'chatting' | 'loading' | 'error';
  collapsed: boolean;
  onCollapse: () => void;
  onClear: () => void;
}> = ({ variant, collapsed, onCollapse, onClear }) => {
  const [draft, setDraft] = useState('');

  if (collapsed) {
    return (
      <aside className="flex w-12 cursor-pointer flex-col items-center justify-between rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] py-3">
        <RobotOutlined className="text-[var(--color-primary)] text-lg" />
        {variant === 'chatting' && (
          <span
            className="rounded-full bg-[var(--color-primary)] px-1.5 py-0.5 text-center text-[10px] font-semibold leading-none text-white"
            style={{ minWidth: 20 }}
          >
            4
          </span>
        )}
        <Button type="text" size="small" onClick={onCollapse} aria-label="展开">
          ‹
        </Button>
      </aside>
    );
  }

  return (
    <aside className="flex w-[420px] flex-shrink-0 flex-col rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)]">
      {/* 对话头 */}
      <div className="flex items-center justify-between border-b border-[var(--color-border)] px-4 py-3">
        <div className="flex items-center gap-2">
          <RobotOutlined className="text-[var(--color-primary)]" />
          <span className="text-sm font-medium">Wiki 助手</span>
          {variant === 'chatting' && (
            <Tag color="processing" className="m-0">
              对话中
            </Tag>
          )}
          {variant === 'loading' && (
            <Tag color="processing" className="m-0">
              思考中
            </Tag>
          )}
          {variant === 'error' && (
            <Tag color="red" className="m-0">
              出错
            </Tag>
          )}
        </div>
        <div className="flex items-center gap-2">
          {variant === 'chatting' && (
            <Button type="link" size="small" className="text-xs" onClick={onClear}>
              新对话
            </Button>
          )}
          <Button type="text" size="small" onClick={onCollapse} aria-label="收起">
            ›
          </Button>
        </div>
      </div>

      {/* 消息列表 */}
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-3">
        {variant === 'empty' && (
          <div className="flex h-full flex-col items-center justify-center text-[var(--color-text-3)]">
            <RobotOutlined style={{ fontSize: 32 }} className="mb-2 opacity-50" />
            <div className="text-sm">试试问点啥?</div>
          </div>
        )}
        {variant === 'error' && (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <div className="text-sm text-[var(--color-fail)]">抱歉,知识库暂时不可用</div>
            <div className="mt-1 text-xs text-[var(--color-text-3)]">请稍后重试,或切换网络</div>
          </div>
        )}
        {(variant === 'chatting' || variant === 'loading') && (
          <>
            {SAMPLE_MSGS.map((m) =>
              m.role === 'user' ? (
                <div key={m.id} className="flex justify-end">
                  <div className="max-w-[80%] rounded-lg bg-[var(--color-primary)] px-3 py-2 text-sm text-white">
                    {m.content}
                  </div>
                </div>
              ) : (
                <div key={m.id} className="flex items-start gap-2">
                  <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-[var(--color-primary-bg-active)]">
                    <RobotOutlined className="text-[var(--color-primary)]" />
                  </div>
                  <div className="flex-1">
                    <div className="rounded-lg bg-[var(--color-fill-1)] px-3 py-2 text-sm leading-6">
                      {m.content}
                    </div>
                    {m.sources && m.sources.length > 0 && (
                      <div className="mt-2 space-y-1">
                        <div className="text-xs text-[var(--color-text-3)]">来源:</div>
                        {m.sources.map((s, i) => (
                          <div
                            key={i}
                            className="cursor-pointer rounded border border-[var(--color-border)] bg-[var(--color-bg)] p-2 text-xs hover:border-[var(--color-primary)]"
                          >
                            <div className="font-medium text-[var(--color-primary)]">
                              {s.title}
                            </div>
                            <div className="mt-1 line-clamp-2 text-[var(--color-text-3)]">
                              {s.snippet}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )
            )}
            {variant === 'loading' && (
              <div className="flex items-start gap-2">
                <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-[var(--color-primary-bg-active)]">
                  <RobotOutlined className="text-[var(--color-primary)]" />
                </div>
                <div className="rounded-lg bg-[var(--color-fill-1)] px-4 py-3">
                  <Spin size="small" />
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* 推荐问题(仅空态) */}
      {variant === 'empty' && (
        <div className="border-t border-[var(--color-border)] px-4 py-2">
          <div className="mb-1 text-xs text-[var(--color-text-3)]">试试:</div>
          <Space wrap size={[4, 4]}>
            {SUGGESTED.map((s) => (
              <Button
                key={s}
                size="small"
                type="dashed"
                className="text-xs"
                onClick={() => setDraft(s)}
              >
                <ThunderboltOutlined /> {s}
              </Button>
            ))}
          </Space>
        </div>
      )}

      {/* 输入 */}
      <div className="border-t border-[var(--color-border)] p-3">
        <Input.TextArea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="问点什么吧,例如:CMDB 录入流程是哪个版本?"
          autoSize={{ minRows: 2, maxRows: 5 }}
          className="text-sm"
          disabled={variant === 'error'}
        />
        <div className="mt-2 flex justify-end">
          <Button type="primary" size="small" disabled={variant === 'error' || !draft.trim()}>
            发送
          </Button>
        </div>
      </div>
    </aside>
  );
};

// ── 整体 Layout ──
const FullLayout: React.FC<{ info: BaseInfo; variant: 'empty' | 'chatting' | 'loading' | 'error' }> = ({
  info,
  variant,
}) => {
  const [collapsed, setCollapsed] = useState(false);
  return (
    <div className="flex h-screen gap-4 bg-[var(--color-secondary)] p-4">
      <div className="flex min-h-0 flex-1 flex-col rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        {/* 顶部 header */}
        <header className="mb-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-5 py-3">
          <h1 className="m-0 text-base font-semibold text-[var(--color-text-1)]">知识库</h1>
          <p className="mb-0 mt-1 text-xs text-[var(--color-text-3)]">
            由 AI 持续构建、以页面为中心、可被多个智能体复用的知识库
          </p>
        </header>
        <BaseInfoPanel info={info} />
      </div>
      <RightPanel
        variant={variant}
        collapsed={collapsed}
        onCollapse={() => setCollapsed(true)}
        onClear={() => undefined}
      />
    </div>
  );
};

const meta: Meta<typeof FullLayout> = {
  title: 'OpsPilot/WikiOverviewFull',
  component: FullLayout,
  parameters: { layout: 'fullscreen' },
  decorators: [
    (Story) => (
      <div className="min-h-screen bg-[var(--color-bg-1)]">
        <Story />
      </div>
    ),
  ],
};

export default meta;
type Story = StoryObj<typeof FullLayout>;

// 4 套基础信息 × 4 个右栏态 = 8 个组合(挑 8 个最关键)

export const DefaultChatting: Story = {
  args: { info: DEFAULT_INFO, variant: 'chatting' },
};
export const DefaultEmpty: Story = {
  args: { info: DEFAULT_INFO, variant: 'empty' },
};
export const DefaultLoading: Story = {
  args: { info: DEFAULT_INFO, variant: 'loading' },
};
export const DefaultError: Story = {
  args: { info: DEFAULT_INFO, variant: 'error' },
};

export const EmptyDataChatting: Story = {
  args: { info: EMPTY_INFO, variant: 'chatting' },
};
export const EmptyDataEmpty: Story = {
  args: { info: EMPTY_INFO, variant: 'empty' },
};

export const LowCoverageChatting: Story = {
  args: { info: LOW_COVERAGE_INFO, variant: 'chatting' },
};
export const LowCoverageError: Story = {
  args: { info: LOW_COVERAGE_INFO, variant: 'error' },
};

export const LotsDataChatting: Story = {
  args: { info: LOTS_INFO, variant: 'chatting' },
};
export const LotsDataEmpty: Story = {
  args: { info: LOTS_INFO, variant: 'empty' },
};
