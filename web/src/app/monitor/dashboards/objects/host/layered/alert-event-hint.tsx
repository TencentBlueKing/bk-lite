'use client';

import React from 'react';
import { Tooltip } from 'antd';
import { InfoCircleOutlined } from '@ant-design/icons';
import { ProSectionTitle } from './section-title';
import '../index.module.scss';

/** 健康概览告警卡旁的口径说明。主机与 MySQL 共用这一份。 */
export const ALERT_KPI_HINT_LINES = [
  { lead: '活跃告警', body: '当前仍未恢复的告警总数，与时间范围无关。' },
  { lead: '下方「事件」', body: '只统计所选时间窗内的触发 / 恢复；窗外仍未恢复的告警不会出现在事件栏。' }
] as const;

/** 事件栏标题旁的口径说明。主机与 MySQL 共用这一份。 */
export const EVENT_RAIL_HINT_LINES = [
  { lead: '事件', body: '当前时间范围内发生的告警触发与恢复。' },
  { lead: '健康概览「告警」', body: '未恢复（活跃）告警总数，不受时间范围过滤；二者口径不同，数量可能不一致。' }
] as const;

export interface ScopeHintLine {
  lead: string;
  body: string;
}

const ALERT_KPI_KEYS = new Set(['alert', 'alerts']);

/** 告警 KPI 才挂说明。其它卡保持原样，计数逻辑不经过这里。 */
export const alertKpiHintLines = (key: string): readonly ScopeHintLine[] | null => (
  ALERT_KPI_KEYS.has(key) ? ALERT_KPI_HINT_LINES : null
);

const stopHintClick = (event: React.SyntheticEvent) => {
  event.preventDefault();
  event.stopPropagation();
};

const hintText = (lines: readonly ScopeHintLine[]) => (
  lines.map((line) => `${line.lead}：${line.body}`).join(' ')
);

function HintBody({ lines }: { lines: readonly ScopeHintLine[] }) {
  return (
    <div className="max-w-[360px] text-[13px] font-normal leading-[1.55] text-[var(--color-text-3)]">
      {lines.map((line) => (
        <p key={line.lead} className="m-0 [&+&]:mt-2.5">
          <strong className="text-[13px] font-semibold text-[var(--color-text-1)]">{line.lead}</strong>：{line.body}
        </p>
      ))}
    </div>
  );
}

/** 标题旁的信息图标。悬停出浅底短说明；点击不冒泡，避免抢走告警卡开抽屉。 */
export function ProInfoHint({
  lines,
  text,
  content,
  label: labelText,
  kind
}: {
  lines?: readonly ScopeHintLine[];
  /** 单句说明。排查路径等没有 lead/body 时走这里。 */
  text?: string;
  /** 气泡里的自定义内容。重点关注步骤流走这里，不再塞长句。 */
  content?: React.ReactNode;
  /** 图标的可读名称。content 没有纯文本时用它。 */
  label?: string;
  kind: string;
}) {
  const label = labelText ?? text ?? (lines ? hintText(lines) : '');
  const title = content ?? (text ? (
    <div className="max-w-[360px] text-[13px] font-normal leading-[1.55] text-[var(--color-text-3)]">
      {text}
    </div>
  ) : (
    <HintBody lines={lines ?? []} />
  ));
  return (
    <span
      className="inline-flex shrink-0 items-center leading-none"
      data-scope-hint={kind}
      onClick={stopHintClick}
      onMouseDown={stopHintClick}
      onPointerDown={stopHintClick}
    >
      <Tooltip
        classNames={{ root: 'lightMetricTooltip' }}
        styles={content ? { root: { maxWidth: 520 } } : undefined}
        title={title}
      >
        <InfoCircleOutlined
          className="cursor-help text-[13px] leading-none text-[var(--color-text-4)] hover:text-[var(--color-primary)]"
          aria-label={label}
        />
      </Tooltip>
    </span>
  );
}

/** 事件栏标题。说明走 hint 槽，不再把手拼图标塞进标题文案。 */
export function ProEventsSectionTitle({ title }: { title: React.ReactNode }) {
  return (
    <ProSectionTitle hint={<ProInfoHint kind="events" lines={EVENT_RAIL_HINT_LINES} />}>
      {title}
    </ProSectionTitle>
  );
}
