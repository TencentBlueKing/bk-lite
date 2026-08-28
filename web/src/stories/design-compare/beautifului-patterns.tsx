'use client';

/**
 * Story-only demos: Beautiful UI interaction/layout patterns,
 * rendered in OpsPilot visual system (semantic tokens + Ant Design).
 * Does NOT copy Beautiful UI dark showcase skin.
 */

import { useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  Button,
  Input,
  Progress,
  Segmented,
  Select,
  Space,
  Tag,
  Typography,
} from 'antd';
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  LoadingOutlined,
  PlusOutlined,
  MinusOutlined,
  SearchOutlined,
} from '@ant-design/icons';

const { Text, Paragraph, Title } = Typography;

const panel: React.CSSProperties = {
  border: '1px solid var(--color-border)',
  borderRadius: 8,
  background: 'var(--color-bg)',
};

const fillPanel: React.CSSProperties = {
  ...panel,
  background: 'var(--color-fill-1)',
};

const muted: React.CSSProperties = {
  color: 'var(--color-text-3)',
  fontSize: 12,
  lineHeight: 1.5,
};

function SectionLabel({
  index,
  title,
  description,
}: {
  index: string;
  title: string;
  description: string;
}) {
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
        <Text type="secondary" style={{ fontVariantNumeric: 'tabular-nums', fontSize: 12 }}>
          {index}
        </Text>
        <Text strong style={{ fontSize: 14, color: 'var(--color-text-1)' }}>
          {title}
        </Text>
      </div>
      <div style={muted}>{description}</div>
    </div>
  );
}

/** Loading: elapsed + mode switch — AntD Segmented, token surface */
export function LoadingStateDemo() {
  const [mode, setMode] = useState<string>('Drive');
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const t = window.setInterval(() => setElapsed((s) => +(s + 0.1).toFixed(1)), 100);
    return () => window.clearInterval(t);
  }, []);

  const cells = useMemo(() => Array.from({ length: 36 }, (_, i) => i), []);

  return (
    <div style={{ ...panel, padding: 16 }}>
      <SectionLabel
        index="01"
        title="Loading"
        description="进度可见：状态文案 + 已用时 + 可切换形态（布局来自 Beautiful UI，视觉用 token）"
      />
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, minHeight: 72 }}>
        {mode === 'Drive' && (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(6, 8px)',
              gap: 3,
            }}
            aria-hidden
          >
            {cells.map((i) => (
              <span
                key={i}
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: 2,
                  background: 'var(--color-primary)',
                  opacity: 0.25 + ((i * 17) % 60) / 100,
                }}
              />
            ))}
          </div>
        )}
        {mode === 'Dots' && (
          <Space size={8}>
            {[0, 1, 2].map((i) => (
              <LoadingOutlined
                key={i}
                style={{ color: 'var(--color-primary)', opacity: 1 - i * 0.25 }}
              />
            ))}
          </Space>
        )}
        {mode === 'Orbit' && (
          <LoadingOutlined style={{ fontSize: 22, color: 'var(--color-primary)' }} />
        )}
        <div>
          <Text strong style={{ color: 'var(--color-text-1)' }}>
            分析中
          </Text>
          <div style={{ ...muted, fontVariantNumeric: 'tabular-nums' }}>{elapsed.toFixed(1)}s</div>
        </div>
      </div>
      <div style={{ marginTop: 12 }}>
        <Segmented
          size="small"
          value={mode}
          onChange={(v) => setMode(String(v))}
          options={['Drive', 'Dots', 'Orbit']}
        />
      </div>
    </div>
  );
}

/** Thinking: compact expand + tabbed traces */
export function ThinkingTraceDemo() {
  const [open, setOpen] = useState(true);
  const [tab, setTab] = useState<string>('Steps');

  const body: Record<string, ReactNode> = {
    Steps: (
      <ol style={{ margin: 0, paddingLeft: 18, color: 'var(--color-text-2)', fontSize: 13 }}>
        <li>读取工作负载探针配置</li>
        <li>对比近 7 天重启与错误率</li>
        <li>生成可回滚修复建议</li>
      </ol>
    ),
    Reasoning: (
      <Paragraph style={{ margin: 0, fontSize: 13, color: 'var(--color-text-2)' }}>
        readinessProbe 缺失与滚动失败相关；优先补探针再谈扩容。
      </Paragraph>
    ),
    Search: (
      <Space wrap size={[6, 6]}>
        <Tag>wiki://k8s-sre/probes</Tag>
        <Tag>runbook://nginx-rollout</Tag>
        <Tag icon={<SearchOutlined />}>metrics://5xx</Tag>
      </Space>
    ),
    Coding: (
      <pre
        style={{
          margin: 0,
          fontSize: 12,
          fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
          color: 'var(--color-text-2)',
          whiteSpace: 'pre-wrap',
        }}
      >
        {`readinessProbe:\n  httpGet:\n    path: /healthz\n    port: 8080`}
      </pre>
    ),
  };

  return (
    <div style={{ ...panel, padding: 16 }}>
      <SectionLabel
        index="02"
        title="Thinking"
        description="默认可折叠的推理轨迹；用 Segmented 切换 Steps / Reasoning / Search / Coding"
      />
      <Button
        type="default"
        block
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        icon={open ? <MinusOutlined /> : <PlusOutlined />}
        style={{
          height: 'auto',
          padding: '8px 12px',
          textAlign: 'left',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'flex-start',
          gap: 8,
          background: 'var(--color-fill-1)',
        }}
      >
        Thought for 4 seconds
      </Button>
      {open ? (
        <div style={{ marginTop: 10 }}>
          <Segmented
            size="small"
            value={tab}
            onChange={(v) => setTab(String(v))}
            options={['Steps', 'Reasoning', 'Search', 'Coding']}
            style={{ marginBottom: 10 }}
          />
          <div style={{ ...fillPanel, padding: 12 }}>{body[tab]}</div>
        </div>
      ) : null}
    </div>
  );
}

/** Streaming + sources + follow-ups */
export function StreamingWithSourcesDemo() {
  return (
    <div style={{ ...panel, padding: 16 }}>
      <SectionLabel
        index="03"
        title="Streaming Text"
        description="答案正文 → 引用 chips → Follow-ups 下一问（布局节奏，不是装饰）"
      />
      <Paragraph style={{ marginBottom: 12, color: 'var(--color-text-1)', fontSize: 14 }}>
        nginx-web 近 24h 重启偏高，无探针窗口 5xx 明显高于基线。建议先补 readinessProbe，再观察错误率。
      </Paragraph>
      <Space wrap size={[6, 6]} style={{ marginBottom: 12 }}>
        <Tag icon={<SearchOutlined />} color="processing">
          10 sources
        </Tag>
        <Tag>CMDB · nginx-web</Tag>
        <Tag>Monitor · 5xx</Tag>
        <Tag>Wiki · probe SOP</Tag>
      </Space>
      <div style={{ ...muted, marginBottom: 6 }}>Follow-ups</div>
      <Space direction="vertical" style={{ width: '100%' }} size={8}>
        <Button block style={{ textAlign: 'left', height: 'auto', padding: '8px 12px' }}>
          对比补探针前后的错误率
        </Button>
        <Button block style={{ textAlign: 'left', height: 'auto', padding: '8px 12px' }}>
          生成可回滚的 patch 预览
        </Button>
      </Space>
    </div>
  );
}

/** Approval as stacked choices */
export function ApprovalChoicesDemo() {
  const [picked, setPicked] = useState<string>('probe');
  const options = [
    { id: 'probe', label: '先补 readinessProbe（推荐）' },
    { id: 'scale', label: '直接扩容副本' },
    { id: 'window', label: '仅预约变更窗口' },
  ];

  return (
    <div style={{ ...panel, padding: 16 }}>
      <SectionLabel
        index="04"
        title="Approval"
        description="人机确认用真实可选列表；选中态清晰，不用色块当唯一语义"
      />
      <Title level={5} style={{ marginTop: 0, marginBottom: 12, fontSize: 14 }}>
        下一步怎么处置 nginx-web？
      </Title>
      <Space direction="vertical" style={{ width: '100%' }} size={8}>
        {options.map((o) => (
          <Button
            key={o.id}
            block
            type={picked === o.id ? 'primary' : 'default'}
            onClick={() => setPicked(o.id)}
            style={{ textAlign: 'left', height: 'auto', padding: '8px 12px' }}
          >
            {o.label}
          </Button>
        ))}
      </Space>
    </div>
  );
}

/** Tool chips */
export function ToolChipsDemo() {
  const chips = [
    { name: 'kubectl_get', status: 'done' as const },
    { name: 'metrics_query', status: 'done' as const },
    { name: 'apply_patch', status: 'running' as const },
    { name: 'request_approval', status: 'pending' as const },
  ];

  return (
    <div style={{ ...panel, padding: 16 }}>
      <SectionLabel
        index="05"
        title="Tool Chips"
        description="工具调用收成紧凑 chip 行，展开细节另说；避免大段 JSON 占屏"
      />
      <div style={{ ...muted, marginBottom: 8 }}>4 tool calls · 2 messages</div>
      <Space wrap size={[8, 8]}>
        {chips.map((c) => (
          <Tag
            key={c.name}
            icon={
              c.status === 'running' ? (
                <LoadingOutlined />
              ) : c.status === 'done' ? (
                <CheckCircleOutlined />
              ) : (
                <ClockCircleOutlined />
              )
            }
            color={
              c.status === 'running' ? 'processing' : c.status === 'done' ? 'success' : 'default'
            }
          >
            {c.name}
          </Tag>
        ))}
      </Space>
    </div>
  );
}

/** Task rows */
export function TaskRowsDemo() {
  const rows = [
    { title: '校验集群凭据', meta: '12 targets', status: 'Completed', progress: 100 },
    { title: '匹配工作负载', meta: '12/12', status: 'Completed', progress: 100 },
    { title: '构建补丁任务', meta: '7 workloads', status: 'Running', progress: 62 },
    { title: '草拟变更说明', meta: '2 drafts', status: 'Queued', progress: 0 },
  ];

  return (
    <div style={{ ...panel, padding: 4 }}>
      <div style={{ padding: '12px 12px 4px' }}>
        <SectionLabel
          index="06"
          title="Task Rows"
          description="Agent 子任务用行列表：状态 + 进度，信息密度高但不堆卡片"
        />
      </div>
      {rows.map((r) => (
        <div
          key={r.title}
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr auto',
            gap: 8,
            padding: '10px 12px',
            borderTop: '1px solid var(--color-border)',
          }}
        >
          <div>
            <Text style={{ fontSize: 13, color: 'var(--color-text-1)' }}>{r.title}</Text>
            <div style={muted}>{r.meta}</div>
            {r.status === 'Running' ? (
              <Progress
                percent={r.progress}
                size="small"
                showInfo={false}
                strokeColor="var(--color-primary)"
                style={{ marginTop: 6, marginBottom: 0 }}
              />
            ) : null}
          </div>
          <Tag
            color={
              r.status === 'Completed' ? 'success' : r.status === 'Running' ? 'processing' : 'default'
            }
            style={{ height: 'fit-content' }}
          >
            {r.status}
          </Tag>
        </div>
      ))}
    </div>
  );
}

export function PromptBarDemo({ compact = false }: { compact?: boolean }) {
  const bar = (
    <>
      {!compact ? (
        <SectionLabel
          index="08"
          title="Prompt Bar"
          description="Composer：模型选择 + 输入 + @引用 / 快捷命令，仍用 AntD Input/Select"
        />
      ) : null}
      <Space.Compact style={{ width: '100%' }}>
        <Select
          defaultValue="gpt-4o"
          style={{ width: 118 }}
          options={[
            { value: 'gpt-4o', label: 'gpt-4o' },
            { value: 'deepseek', label: 'deepseek' },
          ]}
        />
        <Input placeholder="@wiki /patch 说明风险后执行…" aria-label="Prompt composer" />
        <Button type="primary">发送</Button>
      </Space.Compact>
      <Space wrap size={[6, 6]} style={{ marginTop: 8 }}>
        <Tag>@wiki/probes</Tag>
        <Tag>/diff</Tag>
        <Tag>/approve</Tag>
      </Space>
    </>
  );

  if (compact) return <div>{bar}</div>;
  return <div style={{ ...panel, padding: 16 }}>{bar}</div>;
}

export function RecommendationCardDemo() {
  return (
    <div style={{ ...panel, padding: 16 }}>
      <SectionLabel
        index="09"
        title="Recommendation"
        description="建议 + 置信度条 + 备选项 + 主/次操作（AntD Button/Progress）"
      />
      <Text strong style={{ display: 'block', marginBottom: 8, color: 'var(--color-text-1)' }}>
        要我提交这条探针补丁吗？
      </Text>
      <Paragraph style={{ marginBottom: 12, fontSize: 13, color: 'var(--color-text-2)' }}>
        为 nginx-web 增加 readinessProbe，超时 3s，失败阈值 3。预计滚动无中断。
      </Paragraph>
      <div style={{ ...muted, marginBottom: 4 }}>High confidence</div>
      <Progress percent={86} size="small" strokeColor="var(--color-success)" />
      <div style={{ ...muted, margin: '10px 0 6px' }}>Other options</div>
      <Space direction="vertical" style={{ width: '100%' }} size={8}>
        <Button block style={{ textAlign: 'left' }}>
          仅预览 patch，不执行
        </Button>
        <Button block style={{ textAlign: 'left' }}>
          改用启动探针 + 人工窗口
        </Button>
      </Space>
      <Space style={{ marginTop: 12 }}>
        <Button type="primary">Accept</Button>
        <Button>Needs review</Button>
      </Space>
    </div>
  );
}

export function ContextCardsDemo() {
  const cards = [
    {
      title: '探针检查清单',
      chars: '290 characters',
      body: '新工作负载上线前必须配置 readiness/liveness，并在预发验证滚动发布。',
      source: 'PDF · k8s-probe-sop.pdf',
    },
    {
      title: '错误率趋势行',
      chars: '1,250 characters',
      body: 'nginx-web 5xx 在无探针窗口升高 18%；补探针后预发回落。',
      source: 'CSV · 5xx-export.csv',
    },
  ];

  return (
    <div style={{ display: 'grid', gap: 8 }}>
      <SectionLabel
        index="10"
        title="Context Cards"
        description="检索片段：标题 / 摘要 / 来源，弱容器分层，不套卡片套卡片"
      />
      <div style={muted}>All chunks · 32</div>
      {cards.map((c) => (
        <div key={c.title} style={{ ...fillPanel, padding: 12 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
            <Text strong style={{ fontSize: 13 }}>
              {c.title}
            </Text>
            <span style={muted}>{c.chars}</span>
          </div>
          <Paragraph style={{ margin: '6px 0', fontSize: 13, color: 'var(--color-text-2)' }}>
            {c.body}
          </Paragraph>
          <div style={muted}>{c.source}</div>
        </div>
      ))}
    </div>
  );
}

export function ChatComposerDemo() {
  return (
    <div style={{ ...panel, overflow: 'hidden' }}>
      <div style={{ padding: '12px 16px 0' }}>
        <SectionLabel
          index="07"
          title="Chat"
          description="会话区：分段标签 + 推理摘要 + 回复；底部 Composer"
        />
      </div>
      <div style={{ padding: '0 16px 8px' }}>
        <Segmented size="small" options={['排查', '变更']} defaultValue="排查" />
      </div>
      <div style={{ padding: 16, borderTop: '1px solid var(--color-border)', display: 'grid', gap: 10 }}>
        <Tag color="processing">Metrics · 4s</Tag>
        <Paragraph style={{ margin: 0, fontSize: 13, color: 'var(--color-text-2)' }}>
          已拉取 7 天重启与 5xx；无探针窗口显著更高。
        </Paragraph>
        <Tag>Comparison · 2s</Tag>
        <Paragraph style={{ margin: 0, fontSize: 13, color: 'var(--color-text-1)' }}>
          建议先补探针，周末峰值前完成滚动。
        </Paragraph>
      </div>
      <div style={{ padding: 12, borderTop: '1px solid var(--color-border)', background: 'var(--color-fill-1)' }}>
        <PromptBarDemo compact />
      </div>
    </div>
  );
}

/** Full After gallery — OpsPilot skin */
export function BeautifulUiGallery() {
  return (
    <div
      style={{
        display: 'grid',
        gap: 12,
        padding: 4,
        background: 'var(--color-background-body)',
      }}
    >
      <div style={muted}>
        After · 吸收 Beautiful UI 的交互/布局；主题色与 Ant Design 保持 OpsPilot 不变
      </div>
      <LoadingStateDemo />
      <ThinkingTraceDemo />
      <StreamingWithSourcesDemo />
      <ApprovalChoicesDemo />
      <ToolChipsDemo />
      <TaskRowsDemo />
      <ChatComposerDemo />
      <PromptBarDemo />
      <RecommendationCardDemo />
      <ContextCardsDemo />
    </div>
  );
}

/** Compact stack for chat After panels */
export function BeautifulChatStack({
  header,
  extra,
}: {
  header?: ReactNode;
  extra?: ReactNode;
}) {
  return (
    <div style={{ display: 'grid', gap: 10 }}>
      {header}
      <ThinkingTraceDemo />
      <ToolChipsDemo />
      <StreamingWithSourcesDemo />
      {extra}
      <div style={{ ...fillPanel, padding: 12 }}>
        <PromptBarDemo compact />
      </div>
    </div>
  );
}

/** @deprecated alias kept for older story imports */
export function BuiStage({ children, label }: { children: ReactNode; label?: string }) {
  return (
    <div style={{ display: 'grid', gap: 12 }}>
      {label ? <div style={muted}>{label}</div> : null}
      {children}
    </div>
  );
}
