'use client';

import React from 'react';
import { Tooltip } from 'antd';
import { useDashboardText } from '../../../shared/utils/content-i18n';
import { hostCategoryText } from './category-copy';
import { CardAlertDot, cardAlertClass } from './card-alert';
import type { TabAlertLevel } from './tab-level';
import classic from '../index.module.scss';
import styles from './layered.module.scss';

export type ProcessStatusTone = 'calm' | 'warning' | 'danger' | 'neutral' | 'info';

/** 休眠卡悬浮说明。指标描述表没有这句 Linux/Windows 语义，按产品口径写在这里。 */
export const SLEEPING_STATUS_HINT = '休眠：Linux 多为可中断睡眠(S)，含等待 I/O；Windows 为等待态。';

export interface StatusCountItem {
  key: string;
  label: string;
  /** 整数。没有读数时为 null，卡上显示 --。 */
  value: number | null;
  tone: ProcessStatusTone;
  hint?: string;
}

export interface ProcessStatusCounts {
  blocked: number | null;
  zombies: number | null;
  running: number | null;
  sleeping: number | null;
}

const TONE_CLASS: Record<ProcessStatusTone, string> = {
  calm: styles.statusCardCalm,
  warning: styles.statusCardWarning,
  danger: styles.statusCardDanger,
  neutral: styles.statusCardNeutral,
  info: styles.statusCardInfo
};

/** 堆叠条段序与定稿色：运行 → 休眠 → 阻塞 → 僵尸。色值写在样式里，与图例共用。 */
const PROCESS_STACK = [
  { key: 'running', label: '运行' },
  { key: 'sleeping', label: '休眠' },
  { key: 'blocked', label: '阻塞' },
  { key: 'zombies', label: '僵尸' }
] as const;

const STACK_SWATCH: Record<(typeof PROCESS_STACK)[number]['key'], string> = {
  running: styles.stackRunning,
  sleeping: styles.stackSleeping,
  blocked: styles.stackBlocked,
  zombies: styles.stackZombie
};

const formatProcessShare = (count: number, total: number) => {
  if (!(total > 0)) return '0%';
  const pct = (count / total) * 100;
  if (count > 0 && pct < 0.1) return '<0.1%';
  const rounded = Math.round(pct * 10) / 10;
  return `${Number.isInteger(rounded) ? rounded.toFixed(0) : rounded.toFixed(1)}%`;
};

const processStackTip = (label: string, count: number, total: number) => (
  `${label} · ${count} · ${formatProcessShare(count, total)}`
);

const roundCount = (value: number | null) => (
  value == null || !Number.isFinite(value) ? null : Math.round(value)
);

const semanticItem = (
  key: 'blocked' | 'zombies',
  label: string,
  value: number | null,
  keepEmpty: boolean
): StatusCountItem | null => {
  if (value == null && !keepEmpty) return null;
  const tone: ProcessStatusTone = value != null && value >= 1
    ? (key === 'zombies' ? 'danger' : 'warning')
    : 'neutral';
  return { key, label, value, tone };
};

const readingItem = (
  key: string,
  label: string,
  value: number | null,
  tone: ProcessStatusTone,
  hint?: string
): StatusCountItem => ({
  key,
  label,
  value,
  tone,
  hint
});

/**
 * 固定五张卡一行：进程总数（略宽，内嵌堆叠条）→ 运行中 → 休眠 → 阻塞 → 僵尸。
 * 进程总数是后四项之和。句柄、线程不进状态卡。
 * settled=false 时缺读数仍占位显示 --；settled=true 且某卡不可采集时仍占位 --（不造假数、不画箭头）。
 */
export const processStatusView = (
  counts: ProcessStatusCounts,
  options?: { settled?: boolean }
): StatusCountItem[] => {
  const settled = options?.settled !== false;
  const blocked = roundCount(counts.blocked);
  const zombies = roundCount(counts.zombies);
  const running = roundCount(counts.running);
  const sleeping = roundCount(counts.sleeping);
  const states = [running, sleeping, blocked, zombies];
  const total = settled && states.every((value) => value != null)
    ? (running as number) + (sleeping as number) + (blocked as number) + (zombies as number)
    : null;
  return [
    readingItem('total', '进程总数', total, 'info'),
    readingItem('running', '运行中', running, 'info'),
    readingItem('sleeping', '休眠', sleeping, 'info', SLEEPING_STATUS_HINT),
    semanticItem('blocked', '阻塞进程', blocked, true),
    semanticItem('zombies', '僵尸进程', zombies, true)
  ].filter((item): item is StatusCountItem => item != null);
};

const stackCount = (items: StatusCountItem[], key: string) => {
  const value = items.find((item) => item.key === key)?.value;
  return value == null ? null : value;
};

/** 只画在总数卡内：水平堆叠，极小段至少 4px，总数为 0 或未齐时留浅轨。 */
function ProcessStatusStack({ items }: { items: StatusCountItem[] }) {
  const total = stackCount(items, 'total');
  const parts = PROCESS_STACK.map((series) => ({
    ...series,
    value: stackCount(items, series.key)
  }));
  const ready = total != null && total > 0 && parts.every((part) => part.value != null);
  const tips = ready
    ? parts
      .filter((part) => (part.value as number) > 0)
      .map((part) => processStackTip(part.label, part.value as number, total as number))
    : [];
  return (
    <div className="flex w-full min-w-0 flex-col gap-1.5">
      <div
        className="flex h-2 w-full overflow-hidden rounded-full bg-[var(--color-fill-2)]"
        role="group"
        aria-label={ready ? tips.join('，') : '进程状态占比暂无'}
      >
        {ready ? parts.map((part) => {
          const count = part.value as number;
          if (count <= 0) return null;
          const tip = processStackTip(part.label, count, total as number);
          return (
            <Tooltip key={part.key} title={tip}>
              <span
                className={`block h-full min-w-1 ${STACK_SWATCH[part.key]}`}
                style={{ flexGrow: count, flexBasis: 0 }}
                aria-label={tip}
              />
            </Tooltip>
          );
        }) : null}
      </div>
      <div className="flex flex-wrap gap-x-2 gap-y-1">
        {PROCESS_STACK.map((series) => (
          <span
            key={series.key}
            className="inline-flex items-center gap-1 text-[11px] leading-none text-[var(--color-text-3)]"
          >
            <span
              className={`inline-block h-2 w-2 rounded-[2px] ${STACK_SWATCH[series.key]}`}
              aria-hidden
            />
            {series.label}
          </span>
        ))}
      </div>
    </div>
  );
}

/** 进程状态：标签在上，整数 +「个」。不画涨跌箭头、不画 spark。 */
export default function StatusCountRow({
  items,
  leafAlerts
}: {
  items: StatusCountItem[];
  /** 只在达档的阻塞 / 僵尸叶卡右上角打点。外容器不标。 */
  leafAlerts?: { blocked?: TabAlertLevel; zombies?: TabAlertLevel };
}) {
  const { t } = useDashboardText();
  if (!items.length) {
    return (
      <section className={`${classic.panel} ${styles.statusPanel}`}>
        <div className={styles.sectionHead}>
          <div className={`${classic.sectionLabel} ${styles.sectionTitle}`}>进程状态</div>
        </div>
        <div className={styles.note}>暂无进程数据</div>
      </section>
    );
  }
  const labelOf = (item: StatusCountItem) => {
    if (item.key === 'blocked') return hostCategoryText(t, 'blockedProcesses');
    if (item.key === 'zombies') return hostCategoryText(t, 'zombieProcesses');
    return item.label;
  };
  const leafLevel = (key: string) => (
    key === 'blocked' || key === 'zombies' ? leafAlerts?.[key] : undefined
  );
  return (
    <section className={`${classic.panel} ${styles.statusPanel}`}>
      <div className={styles.sectionHead}>
        <div className={`${classic.sectionLabel} ${styles.sectionTitle}`}>进程状态</div>
      </div>
      <div className={styles.statusCards}>
        {items.map((item) => {
          const level = leafLevel(item.key);
          const card = (
            <div className={`${styles.statusCard} ${TONE_CLASS[item.tone]}${item.key === 'total' ? ` ${styles.statusCardTotal}` : ''} ${cardAlertClass(level)}`}>
              <CardAlertDot level={level} />
              <span className={item.hint ? styles.statusHint : styles.statusLabel}>{labelOf(item)}</span>
              <span className={styles.statusValueRow}>
                <span className={styles.statusValue}>{item.value == null ? '--' : item.value}</span>
                {item.value != null ? <span className={styles.statusUnit}>个</span> : null}
              </span>
              {item.key === 'total' ? <ProcessStatusStack items={items} /> : null}
            </div>
          );
          if (!item.hint) return <React.Fragment key={item.key}>{card}</React.Fragment>;
          return (
            <Tooltip key={item.key} title={item.hint}>
              {card}
            </Tooltip>
          );
        })}
      </div>
    </section>
  );
}
