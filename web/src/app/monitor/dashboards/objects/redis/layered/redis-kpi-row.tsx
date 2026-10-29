'use client';

import { alertKpiHintLines, ProInfoHint } from '../../host/layered/alert-event-hint';
import ProDashLoading from '../../host/layered/pro-dash-loading';
import styles from '../../host/layered/layered.module.scss';

export interface RedisKpiTile {
  key: string;
  label: string;
  value: string;
  tone?: string;
  subtitle?: string;
  detail?: string;
  /** 主值是说明句。换行留在 Redis 本地，不改主机 KPI 壳。 */
  prose?: boolean;
  /** 空态种类，供硬刷核对。有数值时不传。 */
  empty?: string;
  /** 告警卡打开共用抽屉。其它卡不传，保持静态数字壳。 */
  onActivate?: () => void;
  expanded?: boolean;
}

function RedisKpiLabel({ item }: { item: RedisKpiTile }) {
  const scopeHint = alertKpiHintLines(item.key);
  if (!scopeHint) {
    return <div className={styles.kpiLabel}>{item.label}</div>;
  }
  return (
    <div className={`${styles.kpiLabel} inline-flex max-w-full items-center gap-1 !overflow-visible`}>
      <span className="min-w-0 truncate">{item.label}</span>
      <ProInfoHint kind="alert" lines={scopeHint} />
    </div>
  );
}

function RedisKpiBody({ item }: { item: RedisKpiTile }) {
  return (
    <>
      <RedisKpiLabel item={item} />
      {item.prose ? (
        <>
          <div className="mt-1 max-w-full whitespace-normal text-[14px] font-semibold leading-5 text-[var(--color-text-1)]">
            {item.value}
          </div>
          {item.detail ? (
            <p className="m-0 mt-1 max-w-full whitespace-normal text-[12px] font-normal leading-5 text-[var(--color-text-2)]">
              {item.detail}
            </p>
          ) : null}
        </>
      ) : (
        <>
          <div className={item.subtitle ? styles.kpiValueRow : undefined}>
            <div className={styles.kpiValue} style={item.tone ? { color: item.tone } : undefined}>
              {item.value}
            </div>
            {item.subtitle ? <div className={styles.kpiAside}>{item.subtitle}</div> : null}
          </div>
          {item.detail ? <div className={styles.kpiMeta}>{item.detail}</div> : null}
        </>
      )}
    </>
  );
}

/** 概览六卡。五张指标的长空态在这里换行；告警卡复用主机口径说明，主机 signal-bar 保持数字壳。 */
export function RedisKpiTileRow({
  items,
  loading = false,
  columns
}: {
  items: RedisKpiTile[];
  loading?: boolean;
  columns?: number;
}) {
  return (
    <div
      className={styles.kpiGrid}
      data-redis-kpi-row=""
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
        const state = item.empty ? 'empty' : 'value';
        if (item.onActivate) {
          return (
            <button
              key={item.key}
              type="button"
              className={styles.kpiCard}
              data-kpi={item.key}
              data-redis-kpi-state={state}
              data-redis-kpi-empty={item.empty || undefined}
              onClick={item.onActivate}
              aria-expanded={Boolean(item.expanded)}
              aria-haspopup="dialog"
            >
              <RedisKpiBody item={item} />
            </button>
          );
        }
        return (
          <div
            key={item.key}
            className={styles.kpiCard}
            data-kpi={item.key}
            data-redis-kpi-state={state}
            data-redis-kpi-empty={item.empty || undefined}
          >
            <RedisKpiBody item={item} />
          </div>
        );
      })}
    </div>
  );
}
