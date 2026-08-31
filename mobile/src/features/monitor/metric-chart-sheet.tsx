'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Popup } from 'antd-mobile';
import { LeftOutline, RightOutline } from 'antd-mobile-icons';
import { MobileResult, MobileSkeleton } from '@/components/mobile-feedback';
import { useAuth } from '@/context/auth';
import { useTranslation } from '@/utils/i18n';
import { getMonitorUnitList, queryMetricRange } from './adapter';
import type { GapInterval } from './gap-intervals';
import MetricSheetEcharts from './metric-sheet-echarts';
import { metricSeriesPoints, type MonitorMetric } from './model';
import { resolveMonitorUnitLabel } from './unit-label';
import styles from './monitor.module.css';

interface Props {
  open: boolean;
  metrics: MonitorMetric[];
  activeIndex: number;
  monitorObjectId: number;
  instanceId: string;
  rangeMinutes: number;
  interval: number | null;
  onClose: () => void;
  onActiveIndexChange: (index: number) => void;
}

function MetricSheetPane({
  metric,
  monitorObjectId,
  instanceId,
  rangeMinutes,
  interval,
  onUnitChange,
}: {
  metric: MonitorMetric;
  monitorObjectId: number;
  instanceId: string;
  rangeMinutes: number;
  interval: number | null;
  onUnitChange?: (unit: string) => void;
}) {
  const { t } = useTranslation();
  const { userInfo } = useAuth();
  const preferences = useMemo(() => ({
    locale: userInfo?.locale || 'en',
    timezone: userInfo?.timezone || 'Asia/Shanghai',
  }), [userInfo?.locale, userInfo?.timezone]);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [unit, setUnit] = useState(metric.unit);
  const [series, setSeries] = useState<ReturnType<typeof metricSeriesPoints>>([]);
  const [gaps, setGaps] = useState<GapInterval[]>([]);
  const [windowMs, setWindowMs] = useState<{ startMs: number; endMs: number } | null>(null);
  const [retryToken, setRetryToken] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setStatus('loading');
    queryMetricRange(monitorObjectId, metric.id, instanceId, metric.unit, rangeMinutes, interval, controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return;
        setSeries(metricSeriesPoints(result));
        setGaps(result.gaps);
        setWindowMs({ startMs: result.startMs, endMs: result.endMs });
        setUnit(result.unit);
        onUnitChange?.(result.unit);
        setStatus('ready');
      })
      .catch((error: unknown) => {
        if (error instanceof Error && error.name !== 'AbortError') setStatus('error');
      });
    return () => controller.abort();
  }, [instanceId, interval, metric, monitorObjectId, onUnitChange, rangeMinutes, retryToken]);

  if (status === 'loading') {
    return <MobileSkeleton label={t('common.loading')} variant="metrics" rows={1} compact />;
  }
  if (status === 'error') {
    return (
      <div className={styles.metricSheetEmptyWrap}>
        <MobileResult
          kind="error"
          title={t('monitor.metricLoadFailed')}
          actionLabel={t('common.retry')}
          onAction={() => setRetryToken((value) => value + 1)}
          compact
        />
      </div>
    );
  }
  if (!series.length || !windowMs) {
    return (
      <div className={styles.metricSheetEmptyWrap}>
        <MobileResult kind="empty" title={t('common.noData')} compact />
      </div>
    );
  }

  return (
    <div className={styles.metricSheetPane}>
      <div className={styles.metricSheetChartWrap}>
        <MetricSheetEcharts
          series={series}
          gaps={gaps}
          unit={unit}
          startMs={windowMs.startMs}
          endMs={windowMs.endMs}
          preferences={preferences}
        />
      </div>
      {series.length > 1 ? (
        <div className={styles.metricSheetMeta}>
          <span>{t('monitor.seriesCount', undefined, { count: series.length })}</span>
        </div>
      ) : null}
    </div>
  );
}

export default function MetricChartSheet({
  open,
  metrics,
  activeIndex,
  monitorObjectId,
  instanceId,
  rangeMinutes,
  interval,
  onClose,
  onActiveIndexChange,
}: Props) {
  const { t } = useTranslation();
  const metric = metrics[activeIndex] || null;
  const canPrev = activeIndex > 0;
  const canNext = activeIndex < metrics.length - 1;
  const [unitList, setUnitList] = useState<Awaited<ReturnType<typeof getMonitorUnitList>>>([]);
  const [displayUnits, setDisplayUnits] = useState<Record<number, string>>({});
  const handleUnitChange = useCallback((unit: string) => {
    if (!metric) return;
    setDisplayUnits((current) => (
      current[metric.id] === unit ? current : { ...current, [metric.id]: unit }
    ));
  }, [metric]);

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    void getMonitorUnitList(controller.signal).then(setUnitList).catch(() => setUnitList([]));
    return () => controller.abort();
  }, [open]);

  const sheetUnitLabel = metric
    ? resolveMonitorUnitLabel(metric.unit, displayUnits[metric.id], unitList)
    : '';

  return (
    <Popup
      visible={open && Boolean(metric)}
      onMaskClick={onClose}
      bodyStyle={{
        height: '52vh',
        borderTopLeftRadius: 16,
        borderTopRightRadius: 16,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      {metric ? (
        <div className={styles.metricSheet}>
          <div className={styles.metricSheetHeader}>
            <button
              type="button"
              className={styles.metricSheetNav}
              disabled={!canPrev}
              aria-label={t('monitor.metricPrev')}
              onClick={() => canPrev && onActiveIndexChange(activeIndex - 1)}
            >
              <LeftOutline />
            </button>
            <div className={styles.metricSheetTitleBlock}>
              <strong className={styles.metricSheetTitle}>
                {metric.displayName}
                {sheetUnitLabel ? `(${sheetUnitLabel})` : ''}
              </strong>
              {metric.name ? <span className={styles.metricSheetKey}>{metric.name}</span> : null}
              <span className={styles.metricSheetIndex}>
                {t('monitor.metricSheetIndex', undefined, {
                  current: activeIndex + 1,
                  total: metrics.length,
                })}
              </span>
            </div>
            <button
              type="button"
              className={styles.metricSheetNav}
              disabled={!canNext}
              aria-label={t('monitor.metricNext')}
              onClick={() => canNext && onActiveIndexChange(activeIndex + 1)}
            >
              <RightOutline />
            </button>
            <button type="button" className={styles.pickerClose} onClick={onClose}>
              {t('common.close')}
            </button>
          </div>
          <div className={styles.metricSheetBody}>
            <MetricSheetPane
              key={`${metric.id}-${rangeMinutes}-${interval ?? 'na'}`}
              metric={metric}
              monitorObjectId={monitorObjectId}
              instanceId={instanceId}
              rangeMinutes={rangeMinutes}
              interval={interval}
              onUnitChange={handleUnitChange}
            />
          </div>
        </div>
      ) : null}
    </Popup>
  );
}
