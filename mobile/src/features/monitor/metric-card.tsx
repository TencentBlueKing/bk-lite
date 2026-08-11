'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { buildSeriesPath, buildSeriesSinglePoint } from './metric-chart-utils';
import { buildMetricQuery, metricSeriesPoints, type MonitorMetric } from './model';
import { getMonitorUnitList, queryMetricRange } from './adapter';
import { resolveMonitorUnitLabel } from './unit-label';
import { useTranslation } from '@/utils/i18n';
import styles from './monitor.module.css';

interface Props {
  metric: MonitorMetric;
  idValues: string[];
  rangeMinutes: number;
  interval: number | null;
  onOpen?: () => void;
}

export default function MetricCard({ metric, idValues, rangeMinutes, interval, onOpen }: Props) {
  const { t } = useTranslation();
  const ref = useRef<HTMLElement>(null);
  const [visible, setVisible] = useState(false);
  const [status, setStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle');
  const [series, setSeries] = useState<ReturnType<typeof metricSeriesPoints>>([]);
  const [windowMs, setWindowMs] = useState<{ startMs: number; endMs: number } | null>(null);
  const [displayUnit, setDisplayUnit] = useState<string | undefined>(undefined);
  const [retryToken, setRetryToken] = useState(0);
  const [unitList, setUnitList] = useState<Awaited<ReturnType<typeof getMonitorUnitList>>>([]);

  useEffect(() => {
    const node = ref.current;
    if (!node || visible) return;
    if (!('IntersectionObserver' in window)) {
      setVisible(true);
      return;
    }
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) setVisible(true);
    }, { rootMargin: '120px' });
    observer.observe(node);
    return () => observer.disconnect();
  }, [visible]);

  useEffect(() => {
    if (!visible) return;
    const controller = new AbortController();
    void getMonitorUnitList(controller.signal)
      .then(setUnitList)
      .catch(() => setUnitList([]));
    return () => controller.abort();
  }, [visible]);

  useEffect(() => {
    if (!visible) return;
    const controller = new AbortController();
    setStatus('loading');
    queryMetricRange(buildMetricQuery(metric, idValues), metric.unit, rangeMinutes, interval, controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return;
        setSeries(metricSeriesPoints(result));
        setWindowMs({ startMs: result.startMs, endMs: result.endMs });
        setDisplayUnit(result.unit);
        setStatus('ready');
      })
      .catch((error: unknown) => {
        if (error instanceof Error && error.name !== 'AbortError') setStatus('error');
      });
    return () => controller.abort();
  }, [idValues, interval, metric, rangeMinutes, retryToken, visible]);

  // Match Web overview / sheet: resolve from unitList by unit_id; do not pass query echo as displayUnit.
  const unitLabel = useMemo(
    () => resolveMonitorUnitLabel(metric.unit, displayUnit, unitList),
    [displayUnit, metric.unit, unitList],
  );

  const sparklines = useMemo(
    () => series.map((item) => ({
      path: buildSeriesPath(item.points, 100, 34, 6, 4, windowMs),
      point: buildSeriesSinglePoint(item.points),
    })),
    [series, windowMs],
  );
  const showChart = status === 'ready' && sparklines.some((item) => item.path || item.point);
  const openable = Boolean(onOpen) && status === 'ready' && series.length > 0;

  return (
    <article
      ref={ref}
      className={`${styles.metricCard}${openable ? ` ${styles.metricCardOpenable}` : ''}`}
      role={openable ? 'button' : undefined}
      tabIndex={openable ? 0 : undefined}
      onClick={openable ? onOpen : undefined}
      onKeyDown={openable ? (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onOpen?.();
        }
      } : undefined}
      aria-label={openable ? t('monitor.openMetricChart', undefined, { name: metric.displayName }) : undefined}
    >
      <div className={styles.metricHead}>
        <div className={styles.metricTitleRow}>
          <span className={styles.metricName}>{metric.displayName}</span>
          {unitLabel ? <span className={styles.metricUnitBadge}>({unitLabel})</span> : null}
        </div>
        {metric.name ? <span className={styles.metricKey}>{metric.name}</span> : null}
      </div>
      <div
        className={`${styles.metricBody}${showChart ? ` ${styles.metricBodyChart}` : ''}`}
        role={status === 'loading' || status === 'idle' ? 'status' : status === 'error' ? 'alert' : undefined}
        aria-label={status === 'loading' || status === 'idle' ? t('common.loading') : undefined}
      >
        {status === 'loading' || status === 'idle' ? (
          <span className={styles.metricBodySkeleton} aria-hidden="true" />
        ) : status === 'error' ? (
          <div className={styles.metricEmpty}>
            <span>{t('monitor.metricLoadFailed')}</span>
            <button
              type="button"
              className={styles.metricRetry}
              onClick={(event) => {
                event.stopPropagation();
                setRetryToken((value) => value + 1);
              }}
            >
              {t('common.retry')}
            </button>
          </div>
        ) : !showChart ? (
          <div className={styles.metricEmpty}>{t('common.noData')}</div>
        ) : (
          <svg className={styles.chart} viewBox="0 0 100 34" preserveAspectRatio="none" role="img" aria-hidden="true">
            <line className={styles.chartBaseline} x1="0" x2="100" y1="32" y2="32" />
            {sparklines.map((item, index) => (
              item.path ? (
                <path
                  className={styles.chartLine}
                  style={{ opacity: Math.max(.42, 1 - index * .18) }}
                  d={item.path}
                  key={`path-${index}`}
                />
              ) : item.point ? (
                <circle
                  className={styles.chartPoint}
                  cx={item.point.cx}
                  cy={item.point.cy}
                  r={2.5}
                  key={`point-${index}`}
                  style={{ opacity: Math.max(.42, 1 - index * .18) }}
                />
              ) : null
            ))}
          </svg>
        )}
      </div>
    </article>
  );
}
