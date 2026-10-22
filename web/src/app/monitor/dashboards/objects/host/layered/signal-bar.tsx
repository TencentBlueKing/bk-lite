'use client';

import React from 'react';
import { Tooltip } from 'antd';
import { alertKpiHintLines, ProInfoHint } from './alert-event-hint';
import { CardAlertDot, cardAlertClass, type CardAlertFold } from './card-alert';
import type { TabAlertLevel } from './tab-level';
import ProDashLoading from './pro-dash-loading';
import styles from './layered.module.scss';

export interface KpiCardModel {
  key: string;
  label: string;
  /** 窄卡保留短标题时，悬浮展示完整名称。 */
  hint?: string;
  value: string;
  tone?: string;
  subtitle?: string;
  detail?: string;
  extra?: React.ReactNode;
  onActivate?: () => void;
  expanded?: boolean;
  /** 本卡达档。不传或 none 时不打点、不加框。 */
  alertLevel?: TabAlertLevel;
  /** 默认实心折角。与折角同色、需要描边时才传 outline。 */
  fold?: CardAlertFold;
}

const KpiLabel = ({ item }: { item: KpiCardModel }) => {
  const scopeHint = alertKpiHintLines(item.key);
  if (!scopeHint) {
    return (
      <div className={styles.kpiLabel}>
        {item.hint ? (
          <Tooltip title={item.hint}>
            <span>{item.label}</span>
          </Tooltip>
        ) : item.label}
      </div>
    );
  }
  return (
    <div className={`${styles.kpiLabel} inline-flex max-w-full items-center gap-1 !overflow-visible`}>
      <span className="min-w-0 truncate">{item.label}</span>
      <ProInfoHint kind="alert" lines={scopeHint} />
    </div>
  );
};

const ValueCardBody = ({ item }: { item: KpiCardModel }) => (
  <>
    <KpiLabel item={item} />
    <div className={item.subtitle ? styles.kpiValueRow : undefined}>
      <div className={styles.kpiValue} style={item.tone ? { color: item.tone } : undefined}>
        {item.value}
      </div>
      {item.subtitle ? <div className={styles.kpiAside}>{item.subtitle}</div> : null}
    </div>
    {item.detail ? <div className={styles.kpiMeta}>{item.detail}</div> : null}
    {item.extra}
  </>
);

/** 概览 KPI：六张数字卡，标题贴顶、主值紧跟。不含环图、饼图或 sparkline。 */
export function KpiStrip({
  items,
  loading = false,
  columns
}: {
  items: KpiCardModel[];
  loading?: boolean;
  /** 可选列数。不传时保持主机六卡栅格，默认关闭任何额外占位。 */
  columns?: number;
}) {
  return (
    <div
      className={styles.kpiGrid}
      style={columns ? { gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` } : undefined}
      aria-busy={loading || undefined}
    >
      {items.map((item) => {
        if (loading) {
          return (
            <div
              key={item.key}
              className={`${styles.kpiCard} ${styles.kpiCardLoading}`}
              data-kpi={item.key}
            >
              <ProDashLoading />
            </div>
          );
        }
        const className = `${styles.kpiCard} ${cardAlertClass(item.alertLevel)}`;
        const body = (
          <>
            <CardAlertDot level={item.alertLevel} fold={item.fold} />
            <ValueCardBody item={item} />
          </>
        );
        return item.onActivate ? (
          <button
            key={item.key}
            type="button"
            className={className}
            data-kpi={item.key}
            onClick={item.onActivate}
            aria-expanded={Boolean(item.expanded)}
            aria-haspopup="dialog"
          >
            {body}
          </button>
        ) : (
          <div key={item.key} className={className} data-kpi={item.key}>
            {body}
          </div>
        );
      })}
    </div>
  );
}
