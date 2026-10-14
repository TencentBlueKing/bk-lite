'use client';

import React from 'react';
import { Tooltip } from 'antd';
import { HOST_PALETTE } from '../config';
import { formatPlain } from './readings';
import classic from '../index.module.scss';
import styles from './layered.module.scss';

const DONUT_SIZE = 52;
const DONUT_STROKE = 7;
const USAGE_WARN = 80;
const USAGE_CRIT = 90;

export type KpiFooter =
  | { kind: 'donut'; percent: number | null }
  | { kind: 'capacity'; load: number | null; cores: number | null };

export interface KpiCardModel {
  key: string;
  label: string;
  /** 窄卡保留短标题时，悬浮展示完整名称。 */
  hint?: string;
  value: string;
  tone?: string;
  subtitle?: string;
  detail?: string;
  /** 主值下方的占比环或核容量条。运行时间 / 告警不传。 */
  footer?: KpiFooter;
  extra?: React.ReactNode;
  onActivate?: () => void;
  expanded?: boolean;
}

const finite = (value: number | null | undefined): value is number => (
  value != null && Number.isFinite(value)
);

const usageStroke = (percent: number) => {
  if (percent >= USAGE_CRIT) return 'var(--color-fail)';
  if (percent >= USAGE_WARN) return 'var(--color-warning)';
  return 'var(--color-primary)';
};

const coreCount = (cores: number | null) => {
  if (!finite(cores) || cores <= 0) return null;
  const rounded = Math.round(cores);
  return rounded > 0 ? rounded : null;
};

const UsageDonut = ({ percent }: { percent: number | null }) => {
  const radius = (DONUT_SIZE - DONUT_STROKE) / 2 - 0.5;
  const center = DONUT_SIZE / 2;
  const circumference = 2 * Math.PI * radius;
  const clamped = finite(percent) ? Math.min(100, Math.max(0, percent)) : 0;
  const full = clamped >= 99.95;
  return (
    <svg
      width={DONUT_SIZE}
      height={DONUT_SIZE}
      viewBox={`0 0 ${DONUT_SIZE} ${DONUT_SIZE}`}
      className="shrink-0 overflow-visible"
      aria-hidden="true"
    >
      <circle
        cx={center}
        cy={center}
        r={radius}
        fill="none"
        stroke="var(--color-fill-3)"
        strokeWidth={DONUT_STROKE}
      />
      {finite(percent) && clamped > 0 ? (
        <circle
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          stroke={usageStroke(percent)}
          strokeWidth={DONUT_STROKE}
          strokeDasharray={full ? undefined : `${(clamped / 100) * circumference} ${circumference}`}
          strokeLinecap="butt"
          transform={`rotate(-90 ${center} ${center})`}
        />
      ) : null}
    </svg>
  );
};

const CapacityBar = ({ load, cores }: { load: number | null; cores: number | null }) => {
  const count = coreCount(cores);
  const loadValue = finite(load) ? load : null;
  if (loadValue == null || count == null) {
    return (
      <Tooltip title="Load1 / 核数">
        <div className="h-2 w-full overflow-hidden rounded-full bg-[var(--color-fill-3)]" aria-hidden="true" />
      </Tooltip>
    );
  }
  const overload = loadValue > count;
  const fill = Math.min(Math.max(loadValue, 0) / count, 1);
  const caption = `${formatPlain(loadValue)} / ${count}`;
  const factor = formatPlain(loadValue / count);
  return (
    <Tooltip title={`Load1 / 核数 ${caption}`}>
      <div className="flex w-full min-w-0 flex-col justify-end gap-1">
        <div className="flex items-baseline justify-between gap-2 text-xs leading-none tabular-nums">
          <span className={overload ? 'text-[var(--color-warning)]' : 'text-[var(--color-text-3)]'}>
            {caption}
          </span>
          {overload ? <span className="text-[var(--color-warning)]">{factor}×</span> : null}
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-[var(--color-fill-3)]" aria-hidden="true">
          <div
            className="h-full rounded-full"
            style={{
              width: `${fill * 100}%`,
              background: overload ? 'var(--color-warning)' : HOST_PALETTE.orange
            }}
          />
        </div>
      </div>
    </Tooltip>
  );
};

const KpiFooterView = ({ footer }: { footer: KpiFooter }) => {
  if (footer.kind === 'donut') {
    return (
      <div className="mt-auto flex h-[52px] items-center justify-center" data-kpi-footer="donut">
        <UsageDonut percent={footer.percent} />
      </div>
    );
  }
  return (
    <div className="mt-auto flex h-[52px] w-full items-end" data-kpi-footer="capacity">
      <CapacityBar load={footer.load} cores={footer.cores} />
    </div>
  );
};

const valueTone = (item: KpiCardModel) => {
  if (item.tone) return item.tone;
  if (item.footer?.kind !== 'capacity') return undefined;
  const count = coreCount(item.footer.cores);
  if (!finite(item.footer.load) || count == null || item.footer.load <= count) return undefined;
  return 'var(--color-warning)';
};

const KpiCardBody = ({ item }: { item: KpiCardModel }) => {
  const tone = valueTone(item);
  return (
    <>
      <div className={classic.statLabel}>
        {item.hint ? (
          <Tooltip title={item.hint}>
            <span>{item.label}</span>
          </Tooltip>
        ) : item.label}
      </div>
      <div className={classic.statBody}>
        <div className={classic.statValue} style={tone ? { color: tone } : undefined}>
          {item.value}
        </div>
        {item.subtitle ? <div className={classic.statMeta}>{item.subtitle}</div> : null}
        {item.detail ? <div className={classic.statMeta}>{item.detail}</div> : null}
        {item.extra}
      </div>
      {item.footer ? <KpiFooterView footer={item.footer} /> : null}
    </>
  );
};

/** 概览 KPI：占比环、核容量条，或无底部图形。 */
export function KpiStrip({ items }: { items: KpiCardModel[] }) {
  return (
    <div className={styles.kpiGrid}>
      {items.map((item) => (
        item.onActivate ? (
          <button
            key={item.key}
            type="button"
            className={`${classic.statCard} ${styles.kpiActivate}`}
            onClick={item.onActivate}
            aria-expanded={Boolean(item.expanded)}
            aria-haspopup="dialog"
          >
            <KpiCardBody item={item} />
          </button>
        ) : (
          <div key={item.key} className={classic.statCard}>
            <KpiCardBody item={item} />
          </div>
        )
      ))}
    </div>
  );
}
