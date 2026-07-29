'use client';

import { useState } from 'react';
import type { Meta, StoryObj } from '@storybook/nextjs';
import { RobotOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { Button, ConfigProvider, Empty, Input, Space, Tag } from 'antd';

// 视觉伴随原型:wiki overview 页左右布局 + 常驻对话
// 左:基本信息 / 右:对话常驻(不再悬浮按钮)
type Tab = 'overview' | 'material' | 'check' | 'build' | 'settings';

interface ProcessingIssue {
  status: 'pending' | 'parsing' | 'building' | 'built' | 'failed' | 'updated' | 'invalid';
  count: number;
}

interface BaseInfo {
  materialCount: number;       // 资料总数
  relationCount: number;       // 关系数
  pendingReviewCount: number;  // 待审核数
  processing: ProcessingIssue[]; // 处理与异常
  recentPages: Array<{ id: string; title: string; type: string; status: string }>;
  recentBuilds: Array<{ id: string; trigger: string; status: string; time: string }>;
  risks: Array<{ id: string; type: string; title: string }>;
  agents: Array<{ id: string; name: string }>;
}

interface ChatMsg {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: Array<{ title: string; snippet: string }>;
  loading?: boolean;
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

const SAMPLE_INFO: BaseInfo = {
  materialCount: 42,
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

const SAMPLE_MSGS: ChatMsg[] = [
  {
    id: 'm1',
    role: 'user',
    content: 'CMDB 资产录入流程的当前版本是哪个?',
  },
  {
    id: 'm2',
    role: 'assistant',
    content: '当前版本是 v3(2026-07-10 构建),基于「运维标准 v2026.06」和「CMDB 数据规范」两份资料生成。',
    sources: [
      { title: 'CMDB 资产录入流程', snippet: '## 流程概述\n1. 资产申请\n2. 审批\n3. 录入...' },
      { title: '运维标准 v2026.06', snippet: '### 资产分类\n按业务影响分 A/B/C 三级...' },
    ],
  },
  {
    id: 'm3',
    role: 'user',
    content: '能不能加一步「合规校验」?',
  },
  {
    id: 'm4',
    role: 'assistant',
    content: '可以,建议在第 3 步前插入「合规校验」环节,自动检查 IP/账号是否在合规列表。要我生成候选版本吗?',
  },
];

const SUGGESTED = [
  '解释最近一次失败的构建',
  '有哪些页面需要重新构建?',
  '知识库的来源覆盖率多少?',
];

const TABS: Array<{ key: Tab; label: string }> = [
  { key: 'overview', label: '概览' },
  { key: 'material', label: '资料' },
  { key: 'check', label: '检查审核' },
  { key: 'build', label: '构建记录' },
  { key: 'settings', label: '设置' },
];

const StatusMeta: Record<string, { color: string; text: string }> = {
  built: { color: 'green', text: '已构建' },
  success: { color: 'green', text: '成功' },
  partial: { color: 'orange', text: '部分成功' },
  source_updated: { color: 'blue', text: '待更新' },
};

function PersistentChatLayout({ info, messages }: { info: BaseInfo; messages: ChatMsg[] }) {
  const [activeTab, setActiveTab] = useState<Tab>('overview');
  const [draft, setDraft] = useState('');

  return (
    <div className="flex h-[820px] flex-col gap-3 bg-[var(--color-bg)] p-4">
      {/* 顶部详情页 header(对应真实页面的"知识库 / 由 AI 持续构建..."区) */}
      <header className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-5 py-3">
        <h1 className="m-0 text-base font-semibold text-[var(--color-text-1)]">知识库</h1>
        <p className="mb-0 mt-1 text-xs text-[var(--color-text-3)]">
          由 AI 持续构建、以页面为中心、可被多个智能体复用的知识库
        </p>
      </header>

      {/* 主体:左侧 tab 菜单 + 内容 / 右侧常驻对话 */}
      <div className="flex min-h-0 flex-1 gap-4">
        {/* 左侧菜单式 tab */}
        <nav className="flex w-32 flex-shrink-0 flex-col gap-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-2">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => setActiveTab(t.key)}
              className={`flex h-9 items-center rounded-md px-3 text-sm transition-colors ${
                activeTab === t.key
                  ? 'bg-[var(--color-primary-bg-active)] font-medium text-[var(--color-primary)]'
                  : 'text-[var(--color-text-2)] hover:bg-[var(--color-fill-1)] hover:text-[var(--color-text-1)]'
              }`}
            >
              {t.label}
            </button>
          ))}
        </nav>

        {/* 概览内容 */}
        {activeTab === 'overview' && (
          <div className="flex-1 space-y-4 overflow-y-auto">
            {/* 摘要 */}
            <div className="grid grid-cols-3 gap-3">
              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
                <div className="text-xs text-[var(--color-text-3)]">资料总数</div>
                <div className="mt-1 text-2xl font-semibold">{info.materialCount}</div>
              </div>
              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
                <div className="text-xs text-[var(--color-text-3)]">关系数</div>
                <div className="mt-1 text-2xl font-semibold">{info.relationCount}</div>
              </div>
              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
                <div className="text-xs text-[var(--color-text-3)]">待审核数</div>
                <div className="mt-1 text-2xl font-semibold">{info.pendingReviewCount}</div>
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
                  <Button
                    type="link"
                    size="small"
                    className="text-xs"
                    onClick={() => setActiveTab('material')}
                  >
                    更多 →
                  </Button>
                </div>
                <ul className="space-y-2 min-h-[148px]">
                  {info.recentPages.slice(0, 5).map((p) => (
                    <li
                      key={p.id}
                      className="flex h-6 items-center justify-between text-xs"
                    >
                      <span className="truncate">{p.title}</span>
                      <Tag color={StatusMeta[p.status]?.color} className="m-0">
                        {StatusMeta[p.status]?.text || p.status}
                      </Tag>
                    </li>
                  ))}
                  {Array.from({ length: Math.max(0, 5 - info.recentPages.length) }).map(
                    (_, i) => (
                      <li
                        key={`pad-p-${i}`}
                        className="flex h-6 items-center text-xs text-transparent"
                        aria-hidden="true"
                      >
                        .
                      </li>
                    )
                  )}
                </ul>
              </section>
              <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="text-sm font-semibold">最近构建</h3>
                  <Button
                    type="link"
                    size="small"
                    className="text-xs"
                    onClick={() => setActiveTab('build')}
                  >
                    更多 →
                  </Button>
                </div>
                <ul className="space-y-2 min-h-[148px]">
                  {info.recentBuilds.slice(0, 5).map((b) => (
                    <li
                      key={b.id}
                      className="flex h-6 items-center justify-between text-xs"
                    >
                      <span className="flex items-center gap-2">
                        <Tag color="blue">{b.trigger}</Tag>
                        <span className="text-[var(--color-text-3)]">{b.time}</span>
                      </span>
                      <Tag color={StatusMeta[b.status]?.color} className="m-0">
                        {StatusMeta[b.status]?.text || b.status}
                      </Tag>
                    </li>
                  ))}
                  {Array.from({ length: Math.max(0, 5 - info.recentBuilds.length) }).map(
                    (_, i) => (
                      <li
                        key={`pad-b-${i}`}
                        className="flex h-6 items-center text-xs text-transparent"
                        aria-hidden="true"
                      >
                        .
                      </li>
                    )
                  )}
                </ul>
              </section>
            </div>

            {/* 风险 + 智能体 */}
            <div className="grid grid-cols-2 gap-4">
              <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
                <h3 className="mb-3 text-sm font-semibold">风险</h3>
                {info.risks.length === 0 ? (
                  <Empty description="暂无风险" />
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
                <Space wrap>
                  {info.agents.map((a) => (
                    <Tag key={a.id} icon={<RobotOutlined />} color="blue">
                      {a.name}
                    </Tag>
                  ))}
                </Space>
              </section>
            </div>
          </div>
        )}
        {activeTab !== 'overview' && (
          <div className="flex flex-1 items-center justify-center text-sm text-[var(--color-text-3)]">
            {TABS.find((t) => t.key === activeTab)?.label} 内容(略)
          </div>
        )}
      </div>

      {/* 右侧:常驻对话 */}
      <aside className="flex w-[420px] flex-shrink-0 flex-col rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)]">
        {/* 对话头 */}
        <div className="flex items-center justify-between border-b border-[var(--color-border)] px-4 py-3">
          <div className="flex items-center gap-2">
            <RobotOutlined className="text-[var(--color-primary)]" />
            <span className="text-sm font-medium">Wiki 助手</span>
            <Tag color="processing" className="m-0">
              对话中
            </Tag>
          </div>
          <Button type="link" size="small" className="text-xs">
            新对话
          </Button>
        </div>

        {/* 消息列表 */}
        <div className="flex-1 space-y-4 overflow-y-auto px-4 py-3">
          {messages.map((m) =>
            m.role === 'user' ? (
              <div key={m.id} className="flex justify-end">
                <div className="max-w-[80%] rounded-lg bg-[var(--color-primary-bg-active)] px-3 py-2 text-sm">
                  {m.content}
                </div>
              </div>
            ) : (
              <div key={m.id} className="space-y-2">
                <div className="flex items-start gap-2">
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
              </div>
            )
          )}
        </div>

        {/* 推荐问题 */}
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

        {/* 输入 */}
        <div className="border-t border-[var(--color-border)] p-3">
          <Input.TextArea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="问点什么吧,例如:CMDB 录入流程是哪个版本?"
            autoSize={{ minRows: 2, maxRows: 5 }}
            className="text-sm"
          />
          <div className="mt-2 flex justify-end">
            <Button type="primary" size="small">
              发送
            </Button>
          </div>
        </div>
      </aside>
    </div>
  );
}

const meta: Meta<typeof PersistentChatLayout> = {
  title: 'opspilot/wiki/overview-persistent-chat',
  component: PersistentChatLayout,
  parameters: { layout: 'fullscreen' },
  decorators: [
    (Story) => (
      <ConfigProvider>
        <div className="min-h-screen bg-[var(--color-bg-1)] p-6">
          <div className="mx-auto max-w-[1400px] rounded-xl bg-[var(--color-bg)] shadow-sm">
            <Story />
          </div>
        </div>
      </ConfigProvider>
    ),
  ],
};

export default meta;
type Story = StoryObj<typeof PersistentChatLayout>;

export const Default: Story = {
  args: {
    info: SAMPLE_INFO,
    messages: SAMPLE_MSGS,
  },
};

export const EmptyChat: Story = {
  args: {
    info: SAMPLE_INFO,
    messages: [],
  },
};

export const WaitingReply: Story = {
  args: {
    info: SAMPLE_INFO,
    messages: [
      ...SAMPLE_MSGS,
      {
        id: 'm5',
        role: 'user',
        content: '生成候选版本',
      },
      {
        id: 'm6',
        role: 'assistant',
        content: '',
        loading: true,
      },
    ],
  },
};

export const NoRisks: Story = {
  args: {
    info: { ...SAMPLE_INFO, risks: [], pendingReviewCount: 0 },
    messages: SAMPLE_MSGS,
  },
};