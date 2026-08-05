'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { MobileSkeleton } from '@/components/mobile-feedback';
import { buildMetricQuery, metricSeriesPoints, type MonitorMetric } from './model';
import { queryMetricRange } from './adapter';
import { useTranslation } from '@/utils/i18n';
import styles from './monitor.module.css';

function formatLatestValue(value: number) {
  const abs = Math.abs(value);
  if (abs >= 100) return String(Math.round(value));
  if (abs >= 10) return value.toFixed(1);
  if (Number.isInteger(value)) return String(value);
  return value.toFixed(2);
}

interface Props {
  metric: MonitorMetric;
  idValues: string[];
  rangeMinutes: number;
  interval: number | null;
}

function seriesPath(points: ReadonlyArray<readonly [number, number]>) {
  if (points.length < 2) return '';
  const values = points.map((point) => point[1]);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  return points.map((point, index) => {
    const x = (index / (points.length - 1)) * 100;
    const y = 30 - ((point[1] - min) / span) * 24;
    return `${index ? 'L' : 'M'} ${x.toFixed(2)} ${y.toFixed(2)}`;
  }).join(' ');
}

export default function MetricCard({ metric, idValues, rangeMinutes, interval }: Props) {
  const { t } = useTranslation();
  const ref = useRef<HTMLElement>(null);
  const [visible, setVisible] = useState(false);
  const [status, setStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle');
  const [unit, setUnit] = useState(metric.unit);
  const [series, setSeries] = useState<ReturnType<typeof metricSeriesPoints>>([]);
  const [retryToken, setRetryToken] = useState(0);

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
    setStatus('loading');
    queryMetricRange(buildMetricQuery(metric, idValues), metric.unit, rangeMinutes, interval, controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return;
        setSeries(metricSeriesPoints(result));
        setUnit(result.unit);
        setStatus('ready');
      })
      .catch((error: unknown) => {
        if (error instanceof Error && error.name !== 'AbortError') setStatus('error');
      });
    return () => controller.abort();
  }, [idValues, interval, metric, rangeMinutes, retryToken, visible]);

  const paths = useMemo(() => series.map((item) => seriesPath(item.points)).filter(Boolean), [series]);
  const latest = series[0]?.points.at(-1)?.[1];

  const valueText = latest === undefined
    ? t('monitor.seriesCount', undefined, { count: series.length })
    : formatLatestValue(latest);
  const showValue = status === 'ready' && series.length > 0;

  return (
    <article ref={ref} className={styles.metricCard}>
      <div className={styles.metricHead}>
        <span className={styles.metricName}>{metric.displayName}</span>
        {showValue && (
          <span className={styles.metricValue}>
            {valueText}
            {latest !== undefined && unit ? <span className={styles.metricUnit}>{unit}</span> : null}
          </span>
        )}
      </div>
      {status === 'loading' || status === 'idle' ? (
        <MobileSkeleton label={t('common.loading')} variant="metrics" rows={1} compact />
      ) : status === 'error' ? (
        <div className={styles.metricEmpty} role="alert">
          <span>{t('monitor.metricLoadFailed')}</span>
          <button type="button" className={styles.metricRetry} onClick={() => setRetryToken((value) => value + 1)}>{t('common.retry')}</button>
        </div>
      ) : series.length === 0 ? (
        <div className={styles.metricEmpty}>{t('monitor.noRangeData')}</div>
      ) : paths.length > 0 ? (
        <svg className={styles.chart} viewBox="0 0 100 34" preserveAspectRatio="none" role="img" aria-label={`${metric.displayName}, ${t('monitor.seriesCount', undefined, { count: series.length })}`}>
          <line className={styles.chartBaseline} x1="0" x2="100" y1="32" y2="32" />
          {paths.map((path, index) => <path className={styles.chartLine} style={{ opacity: Math.max(.42, 1 - index * .18) }} d={path} key={index} />)}
        </svg>
      ) : null}
    </article>
  );
}
