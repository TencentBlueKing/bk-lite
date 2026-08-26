'use client';

import { Alert, Button, Descriptions, Empty, List, Spin, Tag } from 'antd';
import { useTranslation } from '@/utils/i18n';
import type {
  Application3DAlarmDetailData,
  Application3DDetailData,
  Application3DMetricSeriesResult,
} from '@/app/ops-analysis/types/sceneWidget';

interface Application3DDetailProps {
  detail: Application3DDetailData | null;
  alarmDetail: Application3DAlarmDetailData | null;
  metric: Application3DMetricSeriesResult | null;
  loading: boolean;
  alarmLoading: boolean;
  metricLoading: boolean;
  moreAlarmsLoading: boolean;
  error?: string;
  onClose: () => void;
  onRetry: () => void;
  onOpenAlarm: (alarmId: string) => void;
  onCloseAlarm: () => void;
  onNavigateAlarm: (alarmId: string) => void;
  onRetryMetric: () => void;
  onLoadMoreAlarms: () => void;
}

const MetricTrend = ({ metric }: { metric: Application3DMetricSeriesResult }) => {
  const series = (metric.series ?? []).map((item) => ({
    ...item,
    numeric: item.points.filter(
      (point): point is { timestamp: string; value: number } =>
        typeof point.value === 'number' && Number.isFinite(point.value),
    ),
  }));
  const allPoints = series.flatMap((item) => item.numeric);
  if (!allPoints.length) return null;
  const values = allPoints.map((point) => point.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = Math.max(max - min, 1);
  return (
    <svg viewBox="0 0 300 90" className="h-24 w-full" role="img">
      {series.map((item, seriesIndex) => (
        <polyline
          key={item.name}
          points={item.numeric
            .map((point, index) => {
              const x = (index / Math.max(item.numeric.length - 1, 1)) * 300;
              const y = 80 - ((point.value - min) / span) * 70;
              return `${x},${y}`;
            })
            .join(' ')}
          fill="none"
          stroke="var(--color-primary)"
          strokeOpacity={Math.max(0.35, 1 - seriesIndex * 0.2)}
          strokeWidth="3"
        />
      ))}
      {metric.alarmMarker && (
        <line
          x1="150"
          x2="150"
          y1="0"
          y2="90"
          stroke="var(--color-warning)"
          strokeDasharray="4 3"
        />
      )}
    </svg>
  );
};

export default function Application3DDetail({
  detail,
  alarmDetail,
  metric,
  loading,
  alarmLoading,
  metricLoading,
  moreAlarmsLoading,
  error,
  onClose,
  onRetry,
  onOpenAlarm,
  onCloseAlarm,
  onNavigateAlarm,
  onRetryMetric,
  onLoadMoreAlarms,
}: Application3DDetailProps) {
  const { t } = useTranslation();
  const availableAlarms =
    detail?.alarms.state === 'available' ? detail.alarms : null;
  return (
    <aside className="absolute inset-y-3 right-3 z-20 flex w-[min(460px,calc(100%-24px))] flex-col overflow-hidden rounded-lg border border-[var(--color-border-2)] bg-[var(--color-bg-2)]/95 text-[var(--color-text-1)] shadow-2xl backdrop-blur">
      <header className="flex items-center justify-between border-b border-[var(--color-border-2)] px-4 py-3">
        <strong>
          {alarmDetail
            ? t('dashboard.application3DAlarmDetail')
            : detail?.application.name || t('dashboard.application3DDetail')}
        </strong>
        <Button size="small" onClick={alarmDetail ? onCloseAlarm : onClose}>
          {t('common.close')}
        </Button>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {(loading || alarmLoading) && (
          <div className="flex h-full items-center justify-center"><Spin /></div>
        )}
        {error && !loading && !alarmLoading && (
          <Alert
            type="error"
            showIcon
            message={error}
            action={<Button size="small" onClick={onRetry}>{t('common.retry')}</Button>}
          />
        )}
        {!loading && !alarmLoading && !error && alarmDetail && (
          <div className="space-y-4">
            <Alert
              type={alarmDetail.alarm.isNoData ? 'warning' : 'error'}
              showIcon
              message={alarmDetail.alarm.content}
            />
            <Descriptions
              size="small"
              column={1}
              items={[
                { key: 'resource', label: t('dashboard.application3DResource'), children: alarmDetail.alarm.resource.name },
                { key: 'policy', label: t('dashboard.application3DPolicy'), children: alarmDetail.alarm.policy.name },
                { key: 'metric', label: t('dashboard.application3DMetric'), children: alarmDetail.alarm.metric.name || '-' },
                {
                  key: 'notification',
                  label: t('dashboard.application3DNotification'),
                  children: `${alarmDetail.alarm.notification.configured
                    ? t('dashboard.application3DNotificationConfigured')
                    : t('dashboard.application3DNotificationNotConfigured')} · ${t(
                      `dashboard.application3DNotification_${alarmDetail.alarm.notification.state}`,
                    )}`,
                },
              ]}
            />
            <section>
              <div className="mb-2 font-medium">{t('dashboard.application3DMetricTrend')}</div>
              {metricLoading ? <Spin size="small" /> : metric?.state === 'available' ? (
                <>
                  <MetricTrend metric={metric} />
                  <div className="text-xs text-[var(--color-text-3)]">
                    {metric.series?.[0]?.name}
                    {metric.series?.[0]?.unit ? ` (${metric.series[0].unit})` : ''}
                  </div>
                </>
              ) : metric?.state === 'no_snapshot' ? (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('dashboard.application3DNoMetric')} />
              ) : (
                <Alert
                  type="warning"
                  message={t('dashboard.application3DMetricFailed')}
                  action={<Button size="small" onClick={onRetryMetric}>{t('common.retry')}</Button>}
                />
              )}
            </section>
            <div className="flex justify-between">
              <Button
                disabled={!alarmDetail.navigation.previousAlarmId}
                onClick={() => {
                  if (alarmDetail.navigation.previousAlarmId) {
                    onNavigateAlarm(alarmDetail.navigation.previousAlarmId);
                  }
                }}
              >
                {t('dashboard.application3DPreviousAlarm')}
              </Button>
              <Button
                disabled={!alarmDetail.navigation.nextAlarmId}
                onClick={() => {
                  if (alarmDetail.navigation.nextAlarmId) {
                    onNavigateAlarm(alarmDetail.navigation.nextAlarmId);
                  }
                }}
              >
                {t('dashboard.application3DNextAlarm')}
              </Button>
            </div>
          </div>
        )}
        {!loading && !alarmLoading && !error && detail && !alarmDetail && (
          <div className="space-y-4">
            <div className="flex flex-wrap gap-2">
              <Tag>{detail.application.health.state}</Tag>
              <Tag className="text-[var(--color-error)]">
                {t('dashboard.application3DActiveAlarms')}: {detail.application.health.activeAlarmCount ?? '-'}
              </Tag>
            </div>
            {availableAlarms && (
              <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-5">
                {(['critical', 'error', 'warning', 'info'] as const).map((severity) => (
                  <div
                    key={severity}
                    className="rounded border border-[var(--color-border-2)] bg-[var(--color-fill-2)] p-2"
                  >
                    <div className="text-[var(--color-text-3)]">{severity}</div>
                    <strong>{availableAlarms.severityCounts[severity]}</strong>
                  </div>
                ))}
                <div className="rounded border border-[var(--color-border-2)] bg-[var(--color-fill-2)] p-2">
                  <div className="text-[var(--color-text-3)]">no data</div>
                  <strong>{availableAlarms.noDataAlarmCount}</strong>
                </div>
              </div>
            )}
            {detail.application.properties.length > 0 && (
              <Descriptions
                size="small"
                column={1}
                items={detail.application.properties.map((property) => ({
                  key: property.key,
                  label: property.label,
                  children: property.displayValue,
                }))}
              />
            )}
            <section>
              <div className="mb-2 font-medium">{t('dashboard.application3DAlarmList')}</div>
              {detail.alarms.state === 'unavailable' ? (
                <Alert type="warning" showIcon message={t('dashboard.application3DAlarmsUnavailable')} />
              ) : (
                <List
                  size="small"
                  dataSource={detail.alarms.items}
                  locale={{ emptyText: t('dashboard.application3DNoAlarms') }}
                  renderItem={(alarm) => (
                    <List.Item
                      className="cursor-pointer"
                      onClick={() => onOpenAlarm(alarm.id)}
                    >
                      <List.Item.Meta
                        title={alarm.content}
                        description={`${alarm.resource.name} · ${alarm.policyName}`}
                      />
                      <Tag>{alarm.isNoData ? 'NO DATA' : alarm.severity?.label || '-'}</Tag>
                    </List.Item>
                  )}
                />
              )}
              {availableAlarms?.page.hasMore && (
                <div className="mt-3 text-center">
                  <Button loading={moreAlarmsLoading} onClick={onLoadMoreAlarms}>
                    {t('dashboard.application3DLoadMore')}
                  </Button>
                </div>
              )}
            </section>
          </div>
        )}
      </div>
    </aside>
  );
}
