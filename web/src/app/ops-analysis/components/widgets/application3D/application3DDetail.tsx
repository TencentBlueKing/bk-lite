'use client';

import { Alert, Button, Empty, Spin } from 'antd';
import { useMemo, useState } from 'react';
import { useTranslation } from '@/utils/i18n';
import type {
  Application3DAlarmDetailData,
  Application3DDetailData,
  Application3DMetricSeriesResult,
  Application3DSeverity,
  Application3DWallItem,
} from '@/app/ops-analysis/types/sceneWidget';
import {
  buildTrendYTicks,
  formatAlarmDurationSeconds,
  formatAlarmOccurredAt,
  formatTrendAxisTime,
  groupDetailProperties,
  projectTrendX,
  projectTrendY,
  resolveDetailStatus,
  SEVERITY_BADGE,
  SEVERITY_DOT,
  type DetailProperty,
} from './application3DDetailChrome';

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

const TREND_WIDTH = 320;
const TREND_HEIGHT = 140;
const TREND_PAD = { left: 36, right: 48, top: 10, bottom: 24 };

const MetricTrend = ({ metric }: { metric: Application3DMetricSeriesResult }) => {
  const { t } = useTranslation();
  const series = (metric.series ?? []).map((item, index) => ({
    ...item,
    key: item.name || `series-${index}`,
    numeric: item.points
      .map((point) => {
        const ms = Date.parse(point.timestamp);
        if (!Number.isFinite(ms) || typeof point.value !== 'number' || !Number.isFinite(point.value)) {
          return null;
        }
        return { timestampMs: ms, value: point.value };
      })
      .filter((point): point is { timestampMs: number; value: number } => point != null),
  }));
  const allPoints = series.flatMap((item) => item.numeric);
  if (!allPoints.length) return null;

  const thresholdValues = (metric.thresholds ?? [])
    .map((item) => item.value)
    .filter((value) => Number.isFinite(value));
  const valueDomain = [
    ...allPoints.map((point) => point.value),
    ...thresholdValues,
  ];
  let yMin = Math.min(...valueDomain);
  let yMax = Math.max(...valueDomain);
  if (yMin === yMax) {
    const pad = Math.abs(yMin) * 0.1 || 1;
    yMin -= pad;
    yMax += pad;
  } else {
    const pad = (yMax - yMin) * 0.08;
    yMin -= pad;
    yMax += pad;
  }
  const yTicks = buildTrendYTicks(yMin, yMax);
  yMin = Math.min(yMin, yTicks[0]);
  yMax = Math.max(yMax, yTicks[yTicks.length - 1]);

  const xMin = Math.min(...allPoints.map((point) => point.timestampMs));
  const xMax = Math.max(...allPoints.map((point) => point.timestampMs));
  const plotLeft = TREND_PAD.left;
  const plotTop = TREND_PAD.top;
  const plotWidth = TREND_WIDTH - TREND_PAD.left - TREND_PAD.right;
  const plotHeight = TREND_HEIGHT - TREND_PAD.top - TREND_PAD.bottom;
  const xTicks = [xMin, xMin + (xMax - xMin) / 2, xMax];

  const markerMs = metric.alarmMarker
    ? Date.parse(metric.alarmMarker.timestamp)
    : Number.NaN;
  const markerX = Number.isFinite(markerMs)
    ? projectTrendX(markerMs, xMin, xMax, plotLeft, plotWidth)
    : null;

  return (
    <svg
      viewBox={`0 0 ${TREND_WIDTH} ${TREND_HEIGHT}`}
      className="h-36 w-full"
      role="img"
      data-testid="app3d-metric-trend"
    >
      {yTicks.map((tick) => {
        const y = projectTrendY(tick, yMin, yMax, plotTop, plotHeight);
        return (
          <g key={`y-${tick}`}>
            <line
              x1={plotLeft}
              x2={plotLeft + plotWidth}
              y1={y}
              y2={y}
              stroke="rgba(160, 184, 210, 0.18)"
              strokeWidth="1"
            />
            <text
              x={plotLeft - 6}
              y={y + 3}
              textAnchor="end"
              fill="rgba(186, 200, 214, 0.78)"
              fontSize="9"
            >
              {Number.isInteger(tick) ? String(tick) : tick.toFixed(1)}
            </text>
          </g>
        );
      })}
      {xTicks.map((tick, index) => {
        const x = projectTrendX(tick, xMin, xMax, plotLeft, plotWidth);
        return (
          <text
            key={`x-${index}`}
            x={x}
            y={TREND_HEIGHT - 6}
            textAnchor="middle"
            fill="rgba(186, 200, 214, 0.78)"
            fontSize="9"
          >
            {formatTrendAxisTime(tick)}
          </text>
        );
      })}
      {(metric.thresholds ?? []).map((threshold) => {
        const y = projectTrendY(threshold.value, yMin, yMax, plotTop, plotHeight);
        const unit = metric.series?.[0]?.unit;
        const levelLabel = t(
          `dashboard.application3DSeverity_${threshold.level}`,
          threshold.label,
        );
        const label = unit
          ? `${levelLabel} ${threshold.value}${unit}`
          : `${levelLabel} ${threshold.value}`;
        return (
          <g key={`thr-${threshold.level}-${threshold.value}`}>
            <line
              x1={plotLeft}
              x2={plotLeft + plotWidth}
              y1={y}
              y2={y}
              stroke="var(--color-application3d-metric-marker)"
              strokeWidth="1.5"
              data-testid="app3d-threshold-line"
              data-level={threshold.level}
              data-value={threshold.value}
            />
            <text
              x={plotLeft + plotWidth + 4}
              y={y + 3}
              fill="var(--color-application3d-metric-marker)"
              fontSize="9"
              data-testid="app3d-threshold-label"
            >
              {label}
            </text>
          </g>
        );
      })}
      {series.map((item, seriesIndex) => (
        <polyline
          key={item.key}
          points={item.numeric
            .map((point) => {
              const x = projectTrendX(point.timestampMs, xMin, xMax, plotLeft, plotWidth);
              const y = projectTrendY(point.value, yMin, yMax, plotTop, plotHeight);
              return `${x},${y}`;
            })
            .join(' ')}
          fill="none"
          stroke="var(--color-application3d-metric-stroke)"
          strokeOpacity={Math.max(0.35, 1 - seriesIndex * 0.2)}
          strokeWidth="2.5"
        />
      ))}
      {markerX != null && (
        <line
          x1={markerX}
          x2={markerX}
          y1={plotTop}
          y2={plotTop + plotHeight}
          stroke="var(--color-application3d-metric-marker)"
          strokeDasharray="4 3"
          data-testid="app3d-alarm-marker"
          data-marker-x={markerX}
        />
      )}
    </svg>
  );
};

const StatusBadge = ({
  label,
  badgeBg,
  badgeBorder,
  badgeText,
}: {
  label: string;
  badgeBg: string;
  badgeBorder: string;
  badgeText: string;
}) => (
  <span
    className="app3d-status-badge"
    style={{ background: badgeBg, color: badgeText, borderColor: badgeBorder }}
  >
    {label}
  </span>
);

const SeverityBadge = ({
  severity,
  label,
}: {
  severity: Application3DSeverity | null;
  label: string;
}) => {
  const id = severity?.id;
  const tone =
    id === 'critical' || id === 'error' || id === 'warning' || id === 'info'
      ? SEVERITY_BADGE[id]
      : {
        border: 'rgba(140, 156, 176, 0.55)',
        color: 'rgba(198, 208, 220, 0.92)',
        bg: 'rgba(40, 50, 64, 0.45)',
      };
  return (
    <span
      className="app3d-severity-badge"
      style={{
        background: tone.bg,
        borderColor: tone.border,
        color: tone.color,
      }}
    >
      <span className="app3d-severity-badge__dot" />
      {label}
    </span>
  );
};

const PropertySection = ({
  title,
  items,
  valueOnly = false,
}: {
  title: string;
  items: DetailProperty[];
  valueOnly?: boolean;
}) => {
  if (!items.length) return null;
  return (
    <section className="app3d-detail-section">
      <h3 className="app3d-detail-section__title">{title}</h3>
      <div>
        {items.map((item) => (
          valueOnly ? (
            <div key={item.key} className="app3d-detail-field__value py-1">
              {item.displayValue}
            </div>
          ) : (
            <div key={item.key} className="app3d-detail-field">
              <span className="app3d-detail-field__label">{item.label}</span>
              <span className="app3d-detail-field__value">{item.displayValue}</span>
            </div>
          )
        ))}
      </div>
    </section>
  );
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
  const severityStats = (
    ['critical', 'error', 'warning', 'info'] as const
  ).filter(
    (severity) =>
      severity !== 'info' || (availableAlarms?.severityCounts.info ?? 0) > 0,
  );
  const statusSource = detail?.application ?? selected;
  const status = resolveDetailStatus(statusSource, t);
  const [leftPanelSettled, setLeftPanelSettled] = useState(false);
  const propertySections = useMemo(
    () => groupDetailProperties(detail?.application.properties ?? []),
    [detail?.application.properties],
  );
  const alarmCount =
    detail?.application.health.activeAlarmCount
    ?? selected.health.activeAlarmCount;

  return (
    <>
      <div
        className="absolute inset-0 z-40 bg-[var(--color-application3d-detail-mask)]"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        className="app3d-detail-shell absolute left-0 right-0 top-[5%] z-50 mx-auto h-[88%] w-[84%] max-w-[1480px] text-[var(--color-application3d-text)]"
        role="dialog"
        aria-modal="true"
      >
        <div className="app3d-detail-panels min-h-0 flex-1">
          <div
            className={`app3d-biz-panel z-[52] flex h-full flex-col overflow-hidden [perspective:500px]${leftPanelSettled ? ' is-settled' : ''}`}
            data-status-tone={status.tone}
            style={status.leftPanelStyle}
            onAnimationEnd={(event) => {
              if (event.animationName === 'app3d-move-left') {
                setLeftPanelSettled(true);
              }
            }}
          >
            <div className="min-h-0 flex-1 space-y-5 overflow-y-auto [overflow-anchor:none] px-7 pt-7 pb-5">
              <h2 className="m-0 text-[26px] font-semibold tracking-wide text-[rgba(248,250,252,0.98)]">
                {detail?.application.name || selected.name}
              </h2>

              <div className="flex flex-wrap items-center gap-2.5">
                <StatusBadge
                  label={status.statusLabel}
                  badgeBg={status.accent.badgeBg}
                  badgeBorder={status.accent.badgeBorder}
                  badgeText={status.accent.badgeText}
                />
                <span className="app3d-count-chip">
                  {`${t('dashboard.application3DActiveAlarms')}: ${alarmCount ?? '-'}`}
                </span>
              </div>

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
                  {availableAlarms && (
                    <section className="app3d-detail-section">
                      <h3 className="app3d-detail-section__title">
                        {t('dashboard.application3DSeverityStats', '告警级别统计')}
                      </h3>
                      <div
                        className={`grid gap-2.5 ${
                          severityStats.length === 4 ? 'grid-cols-4' : 'grid-cols-3'
                        }`}
                      >
                        {severityStats.map((severity) => (
                          <div key={severity} className="app3d-stat-cell">
                            <div className="app3d-stat-cell__label">
                              <span
                                className="app3d-stat-cell__dot"
                                style={{
                                  background: SEVERITY_DOT[severity],
                                  color: SEVERITY_DOT[severity],
                                }}
                              />
                              {t(`dashboard.application3DSeverity_${severity}`)}
                            </div>
                            <div className="app3d-stat-cell__value">
                              {availableAlarms.severityCounts[severity]}
                            </div>
                          </div>
                        ))}
                      </div>
                    </section>
                  )}

                  <PropertySection
                    title={t('dashboard.application3DSectionBasic', '基本信息')}
                    items={propertySections.basic}
                  />
                  <PropertySection
                    title={t('dashboard.application3DSectionMaintain', '维护信息')}
                    items={propertySections.maintain}
                  />
                  <PropertySection
                    title={t('dashboard.application3DSectionDescription', '描述')}
                    items={propertySections.description}
                    valueOnly
                  />
                  <PropertySection
                    title={t('dashboard.application3DSectionOther', '其他信息')}
                    items={propertySections.other}
                  />
                </>
              )}
            </div>
          </div>

          <div className="app3d-alarm-panel z-[51] flex flex-col overflow-hidden">
            <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6">
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
                  <div className="mb-1 flex items-center justify-between gap-3">
                    <strong className="text-base">{t('dashboard.application3DAlarmDetail')}</strong>
                    <Button size="small" className="app3d-close-cta !h-8 !min-w-0" onClick={onCloseAlarm}>
                      {t('common.close')}
                    </Button>
                  </div>
                  <div className="app3d-alarm-row !cursor-default hover:!bg-[var(--color-application3d-detail-row-bg)]">
                    <div className="min-w-0 flex-1">
                      <div className="app3d-alarm-row__title">{alarmDetail.alarm.content}</div>
                      <div className="app3d-alarm-row__meta">
                        {`${alarmDetail.alarm.resource.name} · ${alarmDetail.alarm.policy.name}`}
                      </div>
                    </div>
                    <SeverityBadge
                      severity={alarmDetail.alarm.severity}
                      label={
                        alarmDetail.alarm.severity
                          ? t(
                              `dashboard.application3DSeverity_${alarmDetail.alarm.severity.id}`,
                              alarmDetail.alarm.severity.label,
                          )
                          : '-'
                      }
                    />
                  </div>
                  <div className="space-y-2 rounded-[12px] border border-[var(--color-application3d-detail-stat-border)] bg-[var(--color-application3d-detail-stat-bg)] px-4 py-3">
                    {[
                      {
                        key: 'resource',
                        label: t('dashboard.application3DResource'),
                        value: alarmDetail.alarm.resource.name,
                      },
                      {
                        key: 'alertType',
                        label: t('dashboard.application3DAlertType'),
                        value: t(`dashboard.application3DAlertType_${alarmDetail.alarm.alertType}`),
                      },
                      {
                        key: 'occurredAt',
                        label: t('dashboard.application3DOccurredAt'),
                        value: formatAlarmOccurredAt(alarmDetail.alarm.occurredAt),
                      },
                      {
                        key: 'duration',
                        label: t('dashboard.application3DDuration'),
                        value: formatAlarmDurationSeconds(alarmDetail.alarm.durationSeconds),
                      },
                      {
                        key: 'policy',
                        label: t('dashboard.application3DPolicy'),
                        value: alarmDetail.alarm.policy.name,
                      },
                      ...(alarmDetail.alarm.metric.name
                        ? [{
                          key: 'metric',
                          label: t('dashboard.application3DMetric'),
                          value: alarmDetail.alarm.metric.name,
                        }]
                        : []),
                      {
                        key: 'notification',
                        label: t('dashboard.application3DNotification'),
                        value: `${alarmDetail.alarm.notification.configured
                          ? t('dashboard.application3DNotificationConfigured')
                          : t('dashboard.application3DNotificationNotConfigured')} · ${t(
                          `dashboard.application3DNotification_${alarmDetail.alarm.notification.state}`,
                          )}`,
                      },
                    ].map((row) => (
                      <div key={row.key} className="app3d-detail-field">
                        <span className="app3d-detail-field__label">{row.label}</span>
                        <span className="app3d-detail-field__value">{row.value}</span>
                      </div>
                    ))}
                    {(alarmDetail.alarm.dimensions ?? []).length > 0 && (
                      <div className="app3d-detail-field !block" data-testid="app3d-dimensions">
                        <div className="app3d-detail-field__label mb-1">
                          {t('dashboard.application3DDimensions')}
                        </div>
                        <div className="space-y-1">
                          {(alarmDetail.alarm.dimensions ?? []).map((dimension) => (
                            <div
                              key={dimension.key}
                              className="flex justify-between gap-3 text-[13px] text-[rgba(220,230,240,0.9)]"
                            >
                              <span className="text-[rgba(180,196,212,0.8)]">{dimension.label}</span>
                              <span>{dimension.displayValue}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                  <section>
                    <div className="mb-2 text-sm font-medium text-[var(--color-application3d-text-subtle)]">
                      {t('dashboard.application3DMetricTrend')}
                    </div>
                    {metricLoading ? <Spin size="small" /> : metric?.state === 'available' ? (
                      <>
                        <MetricTrend metric={{ ...metric, thresholds: metric.thresholds ?? [] }} />
                        {metric.series?.[0]?.name ? (
                          <div
                            className="text-xs text-[var(--color-application3d-text-muted)]"
                            data-testid="app3d-metric-legend"
                          >
                            {metric.series[0].unit
                              ? `${metric.series[0].name} (${metric.series[0].unit})`
                              : metric.series[0].name}
                          </div>
                        ) : null}
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
                  <div className="flex justify-between gap-3 pt-1">
                    <Button
                      className="app3d-close-cta"
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
                      className="app3d-close-cta"
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
                  <div className="mb-5 flex items-end justify-between gap-3">
                    <h3 className="m-0 text-[17px] font-semibold tracking-wide">
                      {t('dashboard.application3DAlarmList')}
                    </h3>
                    <span className="text-[13px] text-[var(--color-application3d-text-muted)]">
                      {t(
                        'dashboard.application3DAlarmTotal',
                        '共 {count} 条',
                        {
                          count: availableAlarms?.activeAlarmCount
                            ?? detail.application.health.activeAlarmCount
                            ?? 0,
                        },
                      )}
                    </span>
                  </div>
                  {detail.alarms.state === 'unavailable' ? (
                    <Alert type="warning" showIcon message={t('dashboard.application3DAlarmsUnavailable')} />
                  ) : detail.alarms.items.length === 0 ? (
                    <Empty
                      image={Empty.PRESENTED_IMAGE_SIMPLE}
                      description={t('dashboard.application3DNoAlarms')}
                    />
                  ) : (
                    <div>
                      {detail.alarms.items.map((alarm) => (
                        <div
                          key={alarm.id}
                          className="app3d-alarm-row"
                          onClick={() => onOpenAlarm(alarm.id)}
                          onKeyDown={(event) => {
                            if (event.key === 'Enter' || event.key === ' ') {
                              event.preventDefault();
                              onOpenAlarm(alarm.id);
                            }
                          }}
                          role="button"
                          tabIndex={0}
                        >
                          <div className="min-w-0 flex-1">
                            <div className="app3d-alarm-row__title">{alarm.content}</div>
                            <div className="app3d-alarm-row__meta">
                              {`${alarm.resource.name} · ${alarm.policyName}`}
                            </div>
                          </div>
                          <SeverityBadge
                            severity={alarm.severity}
                            label={
                              alarm.severity
                                ? t(
                                    `dashboard.application3DSeverity_${alarm.severity.id}`,
                                    alarm.severity.label,
                                )
                                : '-'
                            }
                          />
                        </div>
                      ))}
                    </div>
                  )}
                  {availableAlarms?.page.hasMore && (
                    <div className="mt-3 text-center">
                      <Button
                        className="app3d-close-cta"
                        loading={moreAlarmsLoading}
                        onClick={onLoadMoreAlarms}
                      >
                        {t('dashboard.application3DLoadMore')}
                      </Button>
                    </div>
                  )}
                </section>
              )}
            </div>
          </div>
        </div>

        <button type="button" className="app3d-close-cta" onClick={onClose}>
          {t('common.close')}
        </button>
      </div>
    </>
  );
}
