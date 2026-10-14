'use client';

import React from 'react';
import { Tooltip } from 'antd';
import classic from '../index.module.scss';
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
}

const KpiLabel = ({ item }: { item: KpiCardModel }) => (
  <div className={classic.statLabel}>
    {item.hint ? (
      <Tooltip title={item.hint}>
        <span>{item.label}</span>
      </Tooltip>
    ) : item.label}
  </div>
);

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

/** 概览 KPI：六张卡都只显示标题和主值。运行时间 / 告警与占比卡同一套字号。 */
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
            <ValueCardBody item={item} />
          </button>
        ) : (
          <div key={item.key} className={classic.statCard} data-kpi={item.key}>
            <ValueCardBody item={item} />
          </div>
        )
      ))}
    </div>
  );
}
