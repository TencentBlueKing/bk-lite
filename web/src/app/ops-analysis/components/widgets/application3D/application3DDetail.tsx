'use client';

import { Alert, Button, Descriptions, Empty, List, Spin, Tag } from 'antd';
import { useState } from 'react';
import { useTranslation } from '@/utils/i18n';
import type {
  Application3DAlarmDetailData,
  Application3DDetailData,
  Application3DMetricSeriesResult,
  Application3DWallItem,
} from '@/app/ops-analysis/types/sceneWidget';
import {
  NEON_PANEL,
  resolveNeonLevel,
  type Application3DNeonLevel,
} from './application3DVisual';

interface Application3DDetailProps {
  selected: Application3DWallItem;
  detail: Application3DDetailData | null;
  alarmDetail: Application3DAlarmDetailData | null;
  metric: Application3DMetricSeriesResult | null;
  loading: boolean;
  alarmLoading: boolean;
  metricLoading: boolean;
  moreAlarmsLoading: boolean;
  error?: string;
  alarmError?: string;
  onClose: () => void;
  onRetry: () => void;
  onRetryAlarm: () => void;
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
          stroke="var(--color-application3d-metric-stroke)"
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
          stroke="var(--color-application3d-metric-marker)"
          strokeDasharray="4 3"
        />
      )}
    </svg>
  );
};

const resolvePanelLevel = (
  detail: Application3DDetailData | null,
  selected: Application3DWallItem,
): Application3DNeonLevel => {
  if (detail) return resolveNeonLevel({ health: detail.application.health });
  return resolveNeonLevel(selected);
};

export default function Application3DDetail({
  selected,
  detail,
  alarmDetail,
  metric,
  loading,
  alarmLoading,
  metricLoading,
  moreAlarmsLoading,
  error,
  alarmError,
  onClose,
  onRetry,
  onRetryAlarm,
  onOpenAlarm,
  onCloseAlarm,
  onNavigateAlarm,
  onRetryMetric,
  onLoadMoreAlarms,
}: Application3DDetailProps) {
  const { t } = useTranslation();
  const availableAlarms =
    detail?.alarms.state === 'available' ? detail.alarms : null;
  const level = resolvePanelLevel(detail, selected);
  const panel = NEON_PANEL[level];
  const [leftPanelSettled, setLeftPanelSettled] = useState(false);

  return (
    <>
      <div
        className="absolute inset-0 z-40 bg-[var(--color-application3d-detail-mask)]"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        className="absolute left-0 right-0 top-[10%] z-50 mx-auto flex h-[80%] w-[66%] text-[var(--color-application3d-text)]"
        role="dialog"
        aria-modal="true"
      >
        <div
          className={`app3d-biz-panel z-[52] ml-[33%] flex h-full w-[30%] flex-col backdrop-blur-[5px] [perspective:500px]${leftPanelSettled ? ' is-settled' : ''}`}
          style={{
            background: panel.gradient,
            border: panel.border,
            boxShadow: panel.shadow,
          }}
          onAnimationEnd={(event) => {
            if (event.animationName === 'app3d-move-left') {
              setLeftPanelSettled(true);
            }
          }}
        >
          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto [overflow-anchor:none] px-[26px] pt-6 text-[var(--color-application3d-text)]">
            <h2 className="m-0 text-xl font-bold tracking-wide">
              {detail?.application.name || selected.name}
            </h2>
            {loading && !detail && (
              <div className="flex justify-center py-8"><Spin /></div>
            )}
            {error && !detail && (
              <Alert
                type="error"
                showIcon
                message={error}
                action={<Button size="small" onClick={onRetry}>{t('common.retry')}</Button>}
              />
            )}
            {detail && (
              <>
                <div className="flex flex-wrap gap-2">
                  <Tag color="processing">{detail.application.health.state}</Tag>
                  <Tag color="error">
                    {t('dashboard.application3DActiveAlarms')}:{' '}
                    {detail.application.health.activeAlarmCount ?? '-'}
                  </Tag>
                </div>
                {availableAlarms && (
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    {(['critical', 'error', 'warning', 'info'] as const).map((severity) => (
                      <div
                        key={severity}
                        className="rounded border border-[var(--color-application3d-alarm-panel-border)] bg-[var(--color-application3d-surface-overlay)] p-2"
                      >
                        <div className="text-[var(--color-application3d-text-subtle)]">{severity}</div>
                        <strong>{availableAlarms.severityCounts[severity]}</strong>
                      </div>
                    ))}
                    <div className="rounded border border-[var(--color-application3d-alarm-panel-border)] bg-[var(--color-application3d-surface-overlay)] p-2">
                      <div className="text-[var(--color-application3d-text-subtle)]">no data</div>
                      <strong>{availableAlarms.noDataAlarmCount}</strong>
                    </div>
                  </div>
                )}
                {detail.application.properties.length > 0 && (
                  <Descriptions
                    size="small"
                    column={1}
                    styles={{
                      label: { color: 'var(--color-application3d-text-muted)' },
                      content: { color: 'var(--color-application3d-text)' },
                    }}
                    items={detail.application.properties.map((property) => ({
                      key: property.key,
                      label: property.label,
                      children: property.displayValue,
                    }))}
                  />
                )}
              </>
            )}
          </div>
          <button
            type="button"
            className="mx-[26px] mb-8 h-12 cursor-pointer border-0 bg-[var(--color-application3d-surface-overlay)] text-center text-base text-[var(--color-application3d-text)] hover:bg-[var(--color-application3d-surface-hover)]"
            onClick={onClose}
          >
            {t('common.close')}
          </button>
        </div>

        <div
          className="app3d-alarm-panel absolute z-[51] mt-[1%] flex h-[96%] w-[70%] flex-col overflow-hidden border-2 border-[var(--color-application3d-alarm-panel-border)] bg-[image:var(--color-application3d-alarm-panel-bg)] shadow-[var(--color-application3d-alarm-panel-shadow)] backdrop-blur-[12px]"
        >
          <div className="min-h-0 flex-1 overflow-y-auto p-5 text-[var(--color-application3d-text)]">
            {(loading || alarmLoading) && (
              <div className="flex h-full items-center justify-center"><Spin /></div>
            )}
            {alarmError && !loading && !alarmLoading && (
              <Alert
                type="error"
                showIcon
                message={alarmError}
                action={<Button size="small" onClick={onRetryAlarm}>{t('common.retry')}</Button>}
              />
            )}
            {!loading && !alarmLoading && !alarmError && alarmDetail && (
              <div className="space-y-4">
                <div className="mb-2 flex items-center justify-between">
                  <strong>{t('dashboard.application3DAlarmDetail')}</strong>
                  <Button size="small" onClick={onCloseAlarm}>{t('common.close')}</Button>
                </div>
                <Alert
                  type={alarmDetail.alarm.isNoData ? 'warning' : 'error'}
                  showIcon
                  message={alarmDetail.alarm.content}
                />
                <Descriptions
                  size="small"
                  column={1}
                  styles={{
                    label: { color: 'var(--color-application3d-text-muted)' },
                    content: { color: 'var(--color-application3d-text)' },
                  }}
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
                      <div className="text-xs text-[var(--color-application3d-text-muted)]">
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
            {!loading && !alarmLoading && !alarmError && detail && !alarmDetail && (
              <section>
                <div className="mb-3 text-base font-medium">{t('dashboard.application3DAlarmList')}</div>
                {detail.alarms.state === 'unavailable' ? (
                  <Alert type="warning" showIcon message={t('dashboard.application3DAlarmsUnavailable')} />
                ) : (
                  <List
                    size="small"
                    dataSource={detail.alarms.items}
                    locale={{ emptyText: t('dashboard.application3DNoAlarms') }}
                    renderItem={(alarm) => (
                      <List.Item
                        className="cursor-pointer !border-[var(--color-application3d-alarm-panel-border)] text-[var(--color-application3d-text)]"
                        onClick={() => onOpenAlarm(alarm.id)}
                      >
                        <List.Item.Meta
                          title={<span className="text-[var(--color-application3d-text)]">{alarm.content}</span>}
                          description={
                            <span className="text-[var(--color-application3d-text-muted)]">
                              {`${alarm.resource.name} · ${alarm.policyName}`}
                            </span>
                          }
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
            )}
          </div>
        </div>
      </div>
    </>
  );
}
