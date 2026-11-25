'use client';

import ProDashLoading from '../../host/layered/pro-dash-loading';
import styles from '../../host/layered/layered.module.scss';
import { NginxHint } from './nginx-hint';
import type { NginxHintCopy } from './hints';

export interface NginxKpiTile {
  key: string;
  label: string;
  value: string;
  tone?: string;
  hint?: NginxHintCopy;
  onActivate?: () => void;
  expanded?: boolean;
}

export function NginxKpiRow({
  items,
  loading = false
}: {
  items: NginxKpiTile[];
  loading?: boolean;
}) {
  return (
    <div className={styles.kpiGrid} data-kpi-columns="6" data-nginx-kpi-row="" aria-busy={loading || undefined}>
      {items.map((item) => {
        if (loading) {
          return (
            <div key={item.key} className={`${styles.kpiCard} ${styles.kpiCardLoading}`} data-kpi={item.key}>
              <ProDashLoading />
            </div>
          );
        }
        const body = (
          <>
            <div className={`${styles.kpiLabel} inline-flex max-w-full items-center gap-1`}>
              <span className="min-w-0 truncate">{item.label}</span>
              {item.hint ? <NginxHint copy={item.hint} /> : null}
            </div>
            <div className={styles.kpiValue} style={item.tone ? { color: item.tone } : undefined}>
              {item.value}
            </div>
          </>
        );
        if (item.onActivate) {
          return (
            <button
              key={item.key}
              type="button"
              className={styles.kpiCard}
              data-kpi={item.key}
              onClick={item.onActivate}
              aria-expanded={Boolean(item.expanded)}
              aria-haspopup="dialog"
            >
              {body}
            </button>
          );
        }
        return (
          <div key={item.key} className={styles.kpiCard} data-kpi={item.key} data-nginx-kpi-value={item.value}>
            {body}
          </div>
        );
      })}
    </div>
  );
}
