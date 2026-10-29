'use client';

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
}

/** 概览五卡。长空态在这里换行，主机 signal-bar 保持数字壳。 */
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
        return (
          <div
            key={item.key}
            className={styles.kpiCard}
            data-kpi={item.key}
            data-redis-kpi-state={item.empty ? 'empty' : 'value'}
            data-redis-kpi-empty={item.empty || undefined}
          >
            <div className={styles.kpiLabel}>{item.label}</div>
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
          </div>
        );
      })}
    </div>
  );
}
