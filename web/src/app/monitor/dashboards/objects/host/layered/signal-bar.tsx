'use client';

import React from 'react';
import { Tooltip } from 'antd';
import { HOST_PALETTE } from '../config';
import { formatPlain } from './readings';
import classic from '../index.module.scss';
import styles from './layered.module.scss';

/** 外径与环宽落在规格 64–76 / 8–10。四张占比卡共用。 */
const DONUT_SIZE = 72;
const DONUT_STROKE = 9;
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
  /** 环心主读数。运行时间 / 告警不传。 */
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

const hotTone = (stroke: string) => (
  stroke === 'var(--color-fail)' || stroke === 'var(--color-warning)' ? stroke : undefined
);

interface RingPaint {
  /** 0–1。null 表示无数据，只画浅轨。 */
  ratio: number | null;
  stroke: string;
  textColor: string;
  tip?: string;
}

const usagePaint = (percent: number | null): RingPaint => {
  if (!finite(percent)) {
    return {
      ratio: null,
      stroke: 'var(--color-primary)',
      textColor: 'var(--color-text-3)'
    };
  }
  const stroke = usageStroke(percent);
  return {
    ratio: Math.min(Math.max(percent, 0), 100) / 100,
    stroke,
    textColor: hotTone(stroke) || 'var(--color-text-1)'
  };
};

const loadPaint = (load: number | null, cores: number | null): RingPaint => {
  const count = coreCount(cores);
  const tip = finite(load) && count != null
    ? `Load1 / 核数 ${formatPlain(load)} / ${count}`
    : 'Load1 / 核数';
  if (!finite(load)) {
    return {
      ratio: null,
      stroke: HOST_PALETTE.orange,
      textColor: 'var(--color-text-3)',
      tip
    };
  }
  const overload = count != null && load > count;
  return {
    ratio: count == null ? null : Math.min(Math.max(load, 0) / count, 1),
    stroke: overload ? 'var(--color-warning)' : HOST_PALETTE.orange,
    textColor: overload ? 'var(--color-warning)' : 'var(--color-text-1)',
    tip
  };
};

const paintOf = (footer: KpiFooter): RingPaint => (
  footer.kind === 'donut'
    ? usagePaint(footer.percent)
    : loadPaint(footer.load, footer.cores)
);

const CenterDonut = ({
  value,
  paint
}: {
  value: string;
  paint: RingPaint;
}) => {
  const radius = (DONUT_SIZE - DONUT_STROKE) / 2 - 0.5;
  const center = DONUT_SIZE / 2;
  const circumference = 2 * Math.PI * radius;
  const ratio = paint.ratio;
  const clamped = ratio == null ? 0 : Math.min(1, Math.max(0, ratio));
  const full = clamped >= 0.9995;
  const ring = (
    <div
      className="relative shrink-0"
      style={{ width: DONUT_SIZE, height: DONUT_SIZE }}
      data-kpi-ring="center"
    >
      <svg
        width={DONUT_SIZE}
        height={DONUT_SIZE}
        viewBox={`0 0 ${DONUT_SIZE} ${DONUT_SIZE}`}
        className="block overflow-visible"
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
        {ratio != null && clamped > 0 ? (
          <circle
            cx={center}
            cy={center}
            r={radius}
            fill="none"
            stroke={paint.stroke}
            strokeWidth={DONUT_STROKE}
            strokeDasharray={full ? undefined : `${clamped * circumference} ${circumference}`}
            strokeLinecap="butt"
            transform={`rotate(-90 ${center} ${center})`}
          />
        ) : null}
      </svg>
      <span
        className="absolute inset-0 flex items-center justify-center px-2 text-[13px] font-semibold leading-none tabular-nums"
        style={{ color: paint.textColor }}
        data-kpi-center=""
      >
        {value}
      </span>
    </div>
  );
  if (!paint.tip) return ring;
  return <Tooltip title={paint.tip}>{ring}</Tooltip>;
};

const KpiLabel = ({ item }: { item: KpiCardModel }) => (
  <div className={classic.statLabel}>
    {item.hint ? (
      <Tooltip title={item.hint}>
        <span>{item.label}</span>
      </Tooltip>
    ) : item.label}
  </div>
);

const RingCardBody = ({ item }: { item: KpiCardModel }) => {
  const caption = [item.subtitle, item.detail].filter(Boolean).join(' · ');
  const paint = paintOf(item.footer as KpiFooter);
  return (
    <>
      <KpiLabel item={item} />
      <div className="mt-auto flex w-full min-w-0 flex-col items-center gap-1">
        <CenterDonut value={item.value} paint={paint} />
        {caption ? (
          <Tooltip title={caption}>
            <div
              className="h-4 w-full truncate text-center text-xs leading-4 text-[var(--color-text-3)]"
              data-kpi-caption=""
            >
              {caption}
            </div>
          </Tooltip>
        ) : (
          <div className="h-4 w-full" data-kpi-caption="" />
        )}
        {item.extra}
      </div>
    </>
  );
};

const ValueCardBody = ({ item }: { item: KpiCardModel }) => (
  <>
    <KpiLabel item={item} />
    <div className={classic.statBody}>
      <div className={classic.statValue} style={item.tone ? { color: item.tone } : undefined}>
        {item.value}
      </div>
      {item.subtitle ? <div className={classic.statMeta}>{item.subtitle}</div> : null}
      {item.detail ? <div className={classic.statMeta}>{item.detail}</div> : null}
      {item.extra}
    </div>
  </>
);

const KpiCardBody = ({ item }: { item: KpiCardModel }) => (
  item.footer ? <RingCardBody item={item} /> : <ValueCardBody item={item} />
);

/** 概览 KPI：占比卡为环心数字；运行时间 / 告警只显示主值。 */
export function KpiStrip({ items }: { items: KpiCardModel[] }) {
  return (
    <div className={styles.kpiGrid}>
      {items.map((item) => (
        item.onActivate ? (
          <button
            key={item.key}
            type="button"
            className={`${classic.statCard} ${styles.kpiActivate}`}
            data-kpi={item.key}
            onClick={item.onActivate}
            aria-expanded={Boolean(item.expanded)}
            aria-haspopup="dialog"
          >
            <KpiCardBody item={item} />
          </button>
        ) : (
          <div key={item.key} className={classic.statCard} data-kpi={item.key}>
            <KpiCardBody item={item} />
          </div>
        )
      ))}
    </div>
  );
}
