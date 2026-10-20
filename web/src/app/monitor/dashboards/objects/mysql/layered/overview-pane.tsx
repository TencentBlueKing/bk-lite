'use client';

import React, { useMemo } from 'react';
import { ProEventsSectionTitle } from '../../host/layered/alert-event-hint';
import { KpiTileRow, ProSectionTitle, ThinTimeSeries, type KpiTileModel } from '../../host/layered/pro-chrome';
import EventsRail, { type HostAlertRailEvent } from '../../host/layered/events-rail';
import { HOST_SERIES_COLOR } from '../../host/config';
import { primaryChartSeries } from '../../host/layered/readings';
import FocusShortcutTitle from '../../host/layered/focus-shortcut-title';
import { describeFocusAxis, seriesSampleValues } from '../../host/layered/focus-axis';
import { useProTimeWindow } from '../../host/layered/pro-time-window';
import { clipChartDataToWindow } from '../../../shared/utils/pro-chart-window';
import classic from '../../host/index.module.scss';
import host from '../../host/layered/layered.module.scss';
import {
  buildMysqlFocusCards,
  buildMysqlOverviewKpis,
  type MysqlFocusCard,
  type MysqlHostCandidate,
  type MysqlOverviewReadings
} from './ia';
import MysqlHostRail from './host-rail';
import {
  MYSQL_FOCUS_METRICS,
  MYSQL_HEALTH_METRICS,
  blocksUntilReady
} from './section-loading';
import type { MetricSeries as MysqlMetricSeries } from '../types';

interface OverviewPaneProps {
  readings: MysqlOverviewReadings;
  previous: Pick<MysqlOverviewReadings, 'slowPerSecond' | 'connectionUtilization' | 'bufferPoolHit'>;
  metricMap: Record<string, MysqlMetricSeries | undefined>;
  pendingMetricNames: ReadonlySet<string>;
  statementsCollected: boolean;
  host: MysqlHostCandidate | null;
  hostHref: string;
  hostLoading: boolean;
  cpuPercent: number | null;
  memPercent: number | null;
  alertsOpen: boolean;
  alertEvents: HostAlertRailEvent[];
  eventsLoading: boolean;
  onOpenAlerts: () => void;
  onFocusAlert: (alertId: string) => void;
  onOpenFocus: (card: MysqlFocusCard) => void;
}

const MYSQL_LOADING_KPIS: KpiTileModel[] = ['connections', 'qps', 'slow', 'buffer', 'uptime', 'alerts'].map((key) => ({
  key,
  label: key,
  value: ''
}));

const FOCUS_LOADING = ['慢查询', '连接使用率', '缓冲池命中', '活跃会话'] as const;

const SPARK_METRIC: Record<NonNullable<MysqlFocusCard['spark']>, { name: string; unit: 'counts' | 'cps' | 'percent'; color: string }> = {
  slow: { name: 'mysql_slow_queries_rate', unit: 'cps', color: HOST_SERIES_COLOR.load1 },
  connections: { name: 'mysql_connection_utilization', unit: 'percent', color: HOST_SERIES_COLOR.memUsed },
  buffer: { name: 'mysql_buffer_pool_hit_ratio', unit: 'percent', color: HOST_SERIES_COLOR.cpu },
  active: { name: 'mysql_threads_running', unit: 'counts', color: HOST_SERIES_COLOR.load1 }
};

export default function OverviewPane({
  readings,
  previous,
  metricMap,
  pendingMetricNames,
  statementsCollected,
  host: linkedHost,
  hostHref,
  hostLoading,
  cpuPercent,
  memPercent,
  alertsOpen,
  alertEvents,
  eventsLoading,
  onOpenAlerts,
  onFocusAlert,
  onOpenFocus
}: OverviewPaneProps) {
  const cards = useMemo<KpiTileModel[]>(() => (
    buildMysqlOverviewKpis(readings).map((card) => ({
      key: card.key,
      label: card.label,
      value: card.value,
      subtitle: card.subtitle,
      tone: card.tone,
      onActivate: card.key === 'alerts' ? onOpenAlerts : undefined,
      expanded: card.key === 'alerts' ? alertsOpen : undefined
    }))
  ), [alertsOpen, onOpenAlerts, readings]);
  const focus = useMemo(
    () => buildMysqlFocusCards(readings, previous, statementsCollected),
    [previous, readings, statementsCollected]
  );
  const healthLoading = blocksUntilReady(MYSQL_HEALTH_METRICS, pendingMetricNames);
  const focusLoading = blocksUntilReady(MYSQL_FOCUS_METRICS, pendingMetricNames);
  const proTime = useProTimeWindow();
  const chartWindow = proTime?.window ?? null;

  return (
    <>
      <ProSectionTitle>健康概览</ProSectionTitle>
      {healthLoading ? (
        <KpiTileRow loading items={MYSQL_LOADING_KPIS} />
      ) : (
        <KpiTileRow items={cards} />
      )}
      <MysqlHostRail
        host={linkedHost}
        href={hostHref}
        cpuPercent={cpuPercent}
        memPercent={memPercent}
        loading={hostLoading}
      />

      <ProEventsSectionTitle title="事件" />
      <EventsRail events={alertEvents} loading={eventsLoading} onFocusAlert={onFocusAlert} />

      {focusLoading ? (
        <>
          <ProSectionTitle>重点关注</ProSectionTitle>
          <div className={host.shortcutGrid}>
            {FOCUS_LOADING.map((title) => (
              <ThinTimeSeries
                key={title}
                title={title}
                loading
                data={[]}
                legends={[]}
              />
            ))}
          </div>
        </>
      ) : focus.length > 0 ? (
        <>
          <ProSectionTitle>重点关注</ProSectionTitle>
          <div className={host.shortcutGrid}>
            {focus.map((card) => {
              const spark = card.spark ? SPARK_METRIC[card.spark] : undefined;
              const series = spark ? metricMap[spark.name] : undefined;
              const points = series?.loadState === 'success' ? primaryChartSeries(series.viewData) : [];
              const axisUnit = spark
                ? describeFocusAxis(
                  spark.unit,
                  seriesSampleValues(clipChartDataToWindow(points, chartWindow))
                ).unitLabel
                : '';
              return (
                <div key={card.key} className={`${classic.panel} ${host.shortcutCard}`}>
                  <div className={host.shortcutCopy}>
                    <FocusShortcutTitle label={card.label} unit={axisUnit} />
                    <div className={host.shortcutValue}>{card.value}</div>
                    {card.delta ? (
                      <div className={host.shortcutSub} style={card.deltaTone ? { color: card.deltaTone } : undefined}>
                        {card.delta}
                      </div>
                    ) : null}
                    <button type="button" className={host.jumpBtn} onClick={() => onOpenFocus(card)}>
                      {card.hint}
                    </button>
                  </div>
                  {spark && points.length > 0 ? (
                    <ThinTimeSeries
                      bare
                      numericAxis
                      className={host.focusChart}
                      title=""
                      unit={spark.unit}
                      data={points}
                      legends={[{ label: card.label, color: spark.color }]}
                    />
                  ) : null}
                </div>
              );
            })}
          </div>
        </>
      ) : null}
    </>
  );
}
