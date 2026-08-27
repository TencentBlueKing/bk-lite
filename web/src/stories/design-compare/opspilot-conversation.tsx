'use client';

/**
 * OpsPilot conversation After — LangSmith trajectory craft under OpsPilot tokens.
 * Thought · grouped tools · sources · follow-ups · recommendation
 */
import { useState, type ReactNode } from 'react';
import { Button, Dropdown, Input, Space, Typography } from 'antd';
import { Sender } from '@ant-design/x';
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  DownOutlined,
  ExclamationCircleOutlined,
  LoadingOutlined,
  PictureOutlined,
  RightOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import UserChoiceCard from '@/app/opspilot/components/custom-chat-sse/UserChoiceCard';
import type { UserChoiceRequest } from '@/app/opspilot/types/global';
import Icon from '@/components/icon';
import { CompactConfidenceBar, Surface, afterSys } from './opspilot-after-system';

const { Text, Paragraph } = Typography;
const now = Date.now();

const approvalPending = {
  execution_id: 'exec-chat-1',
  node_id: 'node-1',
  tool_call_id: 'tool-1',
  tool_name: 'apply_kubernetes_patch',
  tool_args: {
    cluster: 'prod-cluster',
    namespace: 'default',
    workload: 'nginx-web',
    patch: 'readinessProbe',
  },
  timeout_seconds: 300,
  received_at: now,
  status: 'pending' as const,
};

const choiceRequest: UserChoiceRequest = {
  execution_id: 'exec-choice-1',
  node_id: 'node-choice-1',
  choice_id: 'choice-1',
  title: '选择变更窗口',
  options: [
    { key: 'tonight', label: '今晚 22:00–24:00（推荐）' },
    { key: 'weekend', label: '周末窗口' },
    { key: 'manual', label: '仅预览，稍后人工执行' },
  ],
  multiple: false,
  min_select: 1,
  max_select: 1,
  default_keys: [],
  display_hint: 'buttons',
  timeout_seconds: 180,
  received_at: now,
  status: 'pending',
};

function Bubble({ role, children }: { role: 'user' | 'assistant'; children: ReactNode }) {
  const isUser = role === 'user';
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[90%] text-[13px] leading-[1.55] text-[var(--color-text-1)] ${
          isUser ? 'rounded-[10px] bg-[var(--color-fill-1)] px-3 py-2' : ''
        }`}
      >
        {children}
      </div>
    </div>
  );
}

function ThoughtBlock() {
  const [open, setOpen] = useState(false);
  return (
    <Surface
      meta={
        <>
          <span>thought · 4.1s</span>
          <span>collapsed by default</span>
        </>
      }
      padded={false}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '8px 10px',
          border: 'none',
          background: 'transparent',
          cursor: 'pointer',
          color: afterSys.text2,
          fontSize: 12.5,
          textAlign: 'left',
        }}
      >
        {open ? <DownOutlined style={{ fontSize: 10 }} /> : <RightOutlined style={{ fontSize: 10 }} />}
        <span>Thought</span>
        <span style={{ color: afterSys.text4, fontFamily: afterSys.mono, fontSize: 11 }}>4.1s</span>
      </button>
      {open && (
        <div style={{ padding: '0 10px 10px', fontSize: 12, color: afterSys.text2, lineHeight: 1.55 }}>
          无 readinessProbe 时流量过早切入；与滚动失败相关。先补探针，再观察 5xx，最后才考虑扩容。
        </div>
      )}
    </Surface>
  );
}

function ToolGroup() {
  const [open, setOpen] = useState(true);
  const tools = [
    { n: 'kubectl_get', s: 'done' as const, ms: '312ms', tokens: '—' },
    { n: 'metrics_query', s: 'done' as const, ms: '1.1s', tokens: '—' },
    { n: 'diff_preview', s: 'running' as const, ms: '…', tokens: '—' },
    { n: 'request_approval', s: 'pending' as const, ms: '—', tokens: '—' },
  ];
  return (
    <Surface
      meta={
        <>
          <span>tools · 4 calls</span>
          <span>parallel group</span>
        </>
      }
      padded={false}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '8px 10px',
          border: 'none',
          background: 'transparent',
          cursor: 'pointer',
          color: afterSys.text2,
          fontSize: 12.5,
        }}
      >
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
          {open ? <DownOutlined style={{ fontSize: 10 }} /> : <RightOutlined style={{ fontSize: 10 }} />}
          Tool calls
        </span>
        <span style={{ fontFamily: afterSys.mono, fontSize: 11, color: afterSys.text4 }}>2 done · 1 run · 1 wait</span>
      </button>
      {open && (
        <div style={{ borderTop: afterSys.divider }}>
          {tools.map((t, i) => (
            <div
              key={t.n}
              style={{
                display: 'grid',
                gridTemplateColumns: '1fr auto auto',
                gap: 10,
                alignItems: 'center',
                padding: '7px 10px',
                borderTop: i === 0 ? undefined : afterSys.divider,
                fontSize: 12,
              }}
            >
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, color: afterSys.text1, minWidth: 0 }}>
                {t.s === 'running' ? (
                  <LoadingOutlined style={{ color: afterSys.primary }} />
                ) : t.s === 'done' ? (
                  <CheckCircleOutlined style={{ color: afterSys.success }} />
                ) : (
                  <ClockCircleOutlined style={{ color: afterSys.text4 }} />
                )}
                <span style={{ fontFamily: afterSys.mono, fontSize: 11.5 }}>{t.n}</span>
              </span>
              <span style={{ fontFamily: afterSys.mono, fontSize: 11, color: afterSys.text4 }}>{t.ms}</span>
              <Button type="link" size="small" style={{ padding: 0, height: 'auto', fontSize: 11 }}>
                Details
              </Button>
            </div>
          ))}
        </div>
      )}
    </Surface>
  );
}

function AssistantMessage() {
  return (
    <Surface
      meta={
        <>
          <span>gpt-4o · 1.8k tok · $0.012</span>
          <span>1.4s</span>
        </>
      }
    >
      <Paragraph style={{ marginBottom: 10, fontSize: 13, color: afterSys.text1 }}>
        nginx-web 近 24h 重启 11 次；无探针窗口 5xx 明显高于基线。建议先补 readinessProbe（超时 3s / 失败阈值 3），再观察错误率。
      </Paragraph>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 10 }}>
        {[
          { icon: true, label: '10 sources' },
          { label: 'CMDB · nginx-web' },
          { label: 'Monitor · 5xx' },
          { label: 'Wiki · probe SOP' },
        ].map((s) => (
          <span
            key={s.label}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 4,
              height: 22,
              padding: '0 8px',
              borderRadius: 999,
              fontSize: 11,
              color: afterSys.text2,
              background: afterSys.fill,
            }}
          >
            {s.icon ? <SearchOutlined style={{ fontSize: 10 }} /> : null}
            {s.label}
          </span>
        ))}
      </div>
      <div style={{ fontSize: 11, color: afterSys.text4, marginBottom: 6 }}>Follow-ups</div>
      <div style={{ display: 'grid', gap: 6 }}>
        {['对比补探针前后的错误率', '生成可回滚的 patch 预览'].map((q) => (
          <button
            key={q}
            type="button"
            style={{
              textAlign: 'left',
              padding: '8px 10px',
              borderRadius: afterSys.radiusSm,
              border: 'none',
              background: afterSys.fill,
              cursor: 'pointer',
              fontSize: 12.5,
              color: afterSys.text1,
              transition: `background ${afterSys.ease}`,
            }}
          >
            {q}
          </button>
        ))}
      </div>
    </Surface>
  );
}

function AfterApprovalCard() {
  const [open, setOpen] = useState(false);

  return (
    <Surface
      meta={
        <>
          <span>approval · apply_kubernetes_patch</span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
            <ClockCircleOutlined style={{ fontSize: 10 }} />
            142s
          </span>
        </>
      }
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <ExclamationCircleOutlined style={{ color: afterSys.warning, fontSize: 14 }} />
        <Text strong style={{ fontSize: 13, color: afterSys.text1 }}>
          需要审批
        </Text>
      </div>
      <div style={{ fontSize: 12, color: afterSys.text3, marginBottom: 8 }}>
        高危变更需人工确认后继续执行。
      </div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 6,
          padding: 0,
          border: 'none',
          background: 'transparent',
          cursor: 'pointer',
          fontSize: 12,
          color: afterSys.text3,
          marginBottom: open ? 8 : 10,
        }}
      >
        {open ? <DownOutlined style={{ fontSize: 10 }} /> : <RightOutlined style={{ fontSize: 10 }} />}
        参数详情
      </button>
      {open && (
        <pre
          style={{
            margin: '0 0 10px',
            padding: '8px 10px',
            borderRadius: afterSys.radiusSm,
            border: afterSys.borderSoft,
            background: afterSys.fill,
            fontSize: 11,
            lineHeight: 1.45,
            color: afterSys.text2,
            fontFamily: afterSys.mono,
            overflow: 'auto',
            maxHeight: 120,
          }}
        >
          {JSON.stringify(approvalPending.tool_args, null, 2)}
        </pre>
      )}
      <Input size="small" placeholder="可选：决策原因" style={{ marginBottom: 10 }} />
      <Space size={8}>
        <Button type="primary" size="small" icon={<CheckCircleOutlined />}>
          批准
        </Button>
        <Button size="small" icon={<CloseCircleOutlined />}>
          拒绝
        </Button>
      </Space>
    </Surface>
  );
}

function ThreadItem({
  title,
  meta,
  time,
  active,
  onClick,
}: {
  title: string;
  meta: string;
  time: string;
  active?: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        width: '100%',
        textAlign: 'left',
        border: 'none',
        borderRadius: afterSys.radiusSm,
        padding: '8px 10px',
        cursor: 'pointer',
        background: active ? afterSys.primaryBg : 'transparent',
        color: active ? afterSys.primary : afterSys.text1,
        transition: `background ${afterSys.ease}, color ${afterSys.ease}`,
      }}
    >
      <div
        style={{
          fontSize: 12.5,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          fontWeight: active ? 600 : 400,
          color: 'inherit',
        }}
      >
        {title}
      </div>
      <div
        style={{
          fontSize: 11,
          marginTop: 2,
          display: 'flex',
          justifyContent: 'space-between',
          color: active ? afterSys.primary : afterSys.text4,
          opacity: active ? 0.85 : 1,
        }}
      >
        <span>{meta}</span>
        <span>{time}</span>
      </div>
    </button>
  );
}

function RecommendationBlock() {
  return (
    <Surface meta={<span>recommendation · confidence</span>}>
      <Text strong style={{ display: 'block', marginBottom: 4, fontSize: 13 }}>
        提交探针补丁？
      </Text>
      <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 8, color: afterSys.text3 }}>
        为 nginx-web 增加 readinessProbe。预计滚动无中断。
      </Paragraph>
      <CompactConfidenceBar percent={86} />
      <Space style={{ marginTop: 10 }} size={8} wrap>
        <Button type="primary" size="small">
          接受
        </Button>
        <Button size="small">需复核</Button>
        <Button size="small" type="link" style={{ paddingInline: 0 }}>
          仅预览
        </Button>
      </Space>
    </Surface>
  );
}

function ChatComposer() {
  const [value, setValue] = useState('');

  return (
    <div style={{ marginTop: 10, flexShrink: 0 }}>
      <div style={{ display: 'flex', justifyContent: 'flex-end', paddingBottom: 8 }}>
        <Button type="text" icon={<Icon type="shanchu" className="text-2xl" />} title="清空对话" aria-label="清空对话" />
      </div>
      <Sender
        value={value}
        onChange={setValue}
        onSubmit={() => setValue('')}
        placeholder="请输入消息..."
        prefix={
          <Button
            type="text"
            icon={<PictureOutlined />}
            title="上传图片"
            aria-label="上传图片"
          />
        }
      />
    </div>
  );
}

export function OpsPilotConversationDemo() {
  return (
    <div className="flex h-full min-h-[560px] flex-col">
      <div
        style={{
          flex: 1,
          overflow: 'auto',
          display: 'grid',
          gap: 12,
          alignContent: 'start',
          paddingRight: 2,
        }}
      >
        <Bubble role="user">nginx-web 最近频繁重启，帮我定位并给出可执行修复。</Bubble>
        <Bubble role="assistant">
          <div style={{ display: 'grid', gap: 8 }}>
            <ThoughtBlock />
            <ToolGroup />
            <AssistantMessage />
            <RecommendationBlock />
            <AfterApprovalCard />
            <Surface meta={<span>user choice · 变更窗口</span>}>
              <UserChoiceCard token="mock-token" onSubmit={() => undefined} request={choiceRequest} />
            </Surface>
          </div>
        </Bubble>
      </div>

      <ChatComposer />
    </div>
  );
}

const STUDIO_APPS = [
  {
    id: 'incident',
    name: 'Incident Copilot',
    icon: 'jiqiren3',
    status: 'Online · Chatflow',
    sessions: [
      { id: '1', title: '排查 nginx 探针', time: '刚刚', meta: '4 tools' },
      { id: '2', title: '扩容 api-gateway', time: '昨天', meta: '2 turns' },
      { id: '3', title: '回滚 payments-v2', time: '周一', meta: 'approved' },
    ],
  },
  {
    id: 'change',
    name: 'Change Copilot',
    icon: 'duihuazhinengti',
    status: 'Online · Chatflow',
    sessions: [
      { id: '4', title: '发布 payments-v3', time: '今天', meta: '1 turn' },
      { id: '5', title: '回滚 api-gateway', time: '周五', meta: 'approved' },
    ],
  },
  {
    id: 'sre',
    name: 'SRE Desk',
    icon: 'jiqirenjiaohukapian',
    status: 'Online · Chatflow',
    sessions: [
      { id: '6', title: '值班交接摘要', time: '1h', meta: '3 turns' },
      { id: '7', title: '磁盘告警收敛', time: '昨天', meta: '2 tools' },
    ],
  },
];

export function OpsPilotChatWorkspace() {
  const [appId, setAppId] = useState(STUDIO_APPS[0].id);
  const currentApp = STUDIO_APPS.find((app) => app.id === appId) ?? STUDIO_APPS[0];
  const [activeSessionId, setActiveSessionId] = useState(currentApp.sessions[0]?.id);

  const switchApp = (id: string) => {
    setAppId(id);
    const next = STUDIO_APPS.find((app) => app.id === id);
    setActiveSessionId(next?.sessions[0]?.id);
  };

  return (
    <div className="flex min-h-[640px] overflow-hidden rounded-md border border-[var(--color-border-1)] bg-[var(--color-bg)]">
      <aside className="flex w-[236px] shrink-0 flex-col border-r border-[var(--color-fill-2)] bg-[var(--color-bg)]">
        <div className="border-b border-[var(--color-fill-2)] px-3 pb-2.5 pt-3">
          <Dropdown
            trigger={['click']}
            placement="bottomLeft"
            menu={{
              items: STUDIO_APPS.map((app) => ({
                key: app.id,
                label: (
                  <div className="flex items-center gap-2 py-0.5">
                    <Icon type={app.icon} className="text-xl text-[var(--color-primary)]" />
                    <span>{app.name}</span>
                  </div>
                ),
                onClick: () => switchApp(app.id),
              })),
            }}
          >
            <button
              type="button"
              className="-mx-1 mb-2 flex w-[calc(100%+8px)] items-center gap-2 rounded-md px-2 py-1 text-left hover:bg-[var(--color-bg-hover)]"
            >
              <Icon type={currentApp.icon} className="shrink-0 text-[28px] text-[var(--color-primary)]" />
              <div className="min-w-0 flex-1">
                <div className="truncate text-[13px] font-semibold tracking-tight text-[var(--color-text-1)]">
                  {currentApp.name}
                </div>
                <div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-[var(--color-text-3)]">
                  <span className="inline-block h-1.5 w-1.5 rounded-full bg-[var(--color-success)]" />
                  {currentApp.status}
                </div>
              </div>
              <Icon type="xiala" className="shrink-0 text-xs text-[var(--color-text-4)]" />
            </button>
          </Dropdown>
          <Button type="primary" size="small" block>
            新对话
          </Button>
        </div>
        <div className="px-2.5 pb-1 pt-2 text-[10.5px] uppercase tracking-[0.04em] text-[var(--color-text-4)]">
          历史对话
        </div>
        <div className="grid gap-1 px-2 pb-3">
          {currentApp.sessions.map((s) => (
            <ThreadItem
              key={s.id}
              title={s.title}
              meta={s.meta}
              time={s.time}
              active={s.id === activeSessionId}
              onClick={() => setActiveSessionId(s.id)}
            />
          ))}
        </div>
      </aside>
      <main className="min-w-0 flex-1 bg-[var(--color-bg)] p-3.5">
        <OpsPilotConversationDemo />
      </main>
    </div>
  );
}
