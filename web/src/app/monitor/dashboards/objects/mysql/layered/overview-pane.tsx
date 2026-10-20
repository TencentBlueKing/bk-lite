'use client';

import React, { useMemo } from 'react';
import { KpiTileRow, ProSectionTitle, ThinTimeSeries, type KpiTileModel } from '../../host/layered/pro-chrome';
import EventsRail, { type HostAlertRailEvent } from '../../host/layered/events-rail';
import { HOST_SERIES_COLOR } from '../../host/config';
import { primaryChartSeries } from '../../host/layered/readings';
import classic from '../../host/index.module.scss';
import host from '../../host/layered/layered.module.scss';
import {
  buildMysqlFocusCards,
  buildMysqlOverviewKpis,
  buildMysqlOverviewTrends,
  type MysqlFocusCard,
  type MysqlHostCandidate,
  type MysqlOverviewReadings,
  type MysqlTrendModel
} from './ia';
import MysqlHostRail from './host-rail';
import {
  MYSQL_BUFFER_TREND_METRICS,
  MYSQL_FOCUS_METRICS,
  MYSQL_HEALTH_METRICS,
  MYSQL_INNODB_TREND_METRICS,
  MYSQL_TREND_SLOTS,
  blocksUntilReady
} from './section-loading';
import type { MetricSeries as MysqlMetricSeries, MetricUnit } from '../types';

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

const SLOT_UNIT: Record<(typeof MYSQL_TREND_SLOTS)[number]['key'], MetricUnit> = {
  connections: 'counts',
  qps: 'cps',
  slow: 'cps'
};

function TrendCard({
  title,
  unit,
  chart,
  loading
}: {
  title: string;
  unit: MetricUnit;
  chart?: MysqlTrendModel;
  loading: boolean;
}) {
  if (chart) {
    return (
      <ThinTimeSeries
        title={chart.title}
        unit={chart.unit}
        data={chart.data}
        legends={chart.legends}
        loading={loading}
      />
    );
  }
  return (
    <ThinTimeSeries
      title={title}
      unit={unit}
      loading={loading}
      emptyText="暂无数据"
      data={[]}
      legends={[]}
    />
  );
}

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
  const trends = useMemo(() => buildMysqlOverviewTrends(metricMap), [metricMap]);
  const trendByKey = useMemo(() => {
    const map = new Map<string, MysqlTrendModel>();
    [...trends.row, ...trends.extra].forEach((chart) => map.set(chart.key, chart));
    return map;
  }, [trends]);
  const healthLoading = blocksUntilReady(MYSQL_HEALTH_METRICS, pendingMetricNames);
  const focusLoading = blocksUntilReady(MYSQL_FOCUS_METRICS, pendingMetricNames);
  const bufferLoading = blocksUntilReady(MYSQL_BUFFER_TREND_METRICS, pendingMetricNames);
  const innodbLoading = blocksUntilReady(MYSQL_INNODB_TREND_METRICS, pendingMetricNames);
  const bufferChart = trendByKey.get('buffer');
  const innodbChart = trendByKey.get('innodb');
  const fourth = bufferChart
    ? { title: '缓冲池命中', unit: 'percent' as const, chart: bufferChart, loading: false }
    : bufferLoading
      ? { title: '缓冲池命中', unit: 'percent' as const, chart: undefined, loading: true }
      : innodbChart
        ? { title: innodbChart.title, unit: innodbChart.unit, chart: innodbChart, loading: false }
        : innodbLoading
          ? { title: 'InnoDB 读写', unit: 'cps' as const, chart: undefined, loading: true }
          : { title: '缓冲池命中', unit: 'percent' as const, chart: undefined, loading: false };
  const extra = trends.extra.filter((chart) => chart.key !== fourth.chart?.key);

  return (
    <>
      <ProSectionTitle>健康概览</ProSectionTitle>
      {healthLoading ? (
        <KpiTileRow loading items={MYSQL_LOADING_KPIS} />
      ) : (
        <KpiTileRow items={cards} />
      )}

      <ProSectionTitle>所属主机</ProSectionTitle>
      <MysqlHostRail
        host={linkedHost}
        href={hostHref}
        cpuPercent={cpuPercent}
        memPercent={memPercent}
        loading={hostLoading}
      />

      <ProSectionTitle>事件</ProSectionTitle>
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
              return (
                <div key={card.key} className={`${classic.panel} ${host.shortcutCard}`}>
                  <div className={host.shortcutCopy}>
                    <div className={host.shortcutLabel}>{card.label}</div>
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

      <ProSectionTitle>实例趋势</ProSectionTitle>
      <div className={host.chartGrid4}>
        {MYSQL_TREND_SLOTS.map((slot) => (
          <TrendCard
            key={slot.key}
            title={slot.title}
            unit={SLOT_UNIT[slot.key]}
            chart={trendByKey.get(slot.key)}
            loading={blocksUntilReady(slot.names, pendingMetricNames)}
          />
        ))}
        <TrendCard
          key={fourth.chart?.key || fourth.title}
          title={fourth.title}
          unit={fourth.unit}
          chart={fourth.chart}
          loading={fourth.loading}
        />
      </div>
      {extra.length > 0 ? (
        <div className={host.chartGrid2}>
          {extra.map((chart) => (
            <TrendCard
              key={chart.key}
              title={chart.title}
              unit={chart.unit}
              chart={chart}
              loading={false}
            />
          ))}
        </div>
      ) : null}
    </>
  );
}
