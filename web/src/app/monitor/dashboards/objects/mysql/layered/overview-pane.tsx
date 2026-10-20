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
  readMysqlRoleBlock,
  type MysqlFocusCard,
  type MysqlOverviewReadings
} from './ia';
import MysqlHostRail from './host-rail';
import MysqlRoleBlock from './role-block';
import type { MysqlHostCandidate } from './ia';
import type { MetricSeries as MysqlMetricSeries } from '../types';

interface OverviewPaneProps {
  readings: MysqlOverviewReadings;
  previous: Pick<MysqlOverviewReadings, 'slowPerSecond' | 'connectionUtilization' | 'bufferPoolHit'>;
  metricMap: Record<string, MysqlMetricSeries | undefined>;
  loading: boolean;
  statementsCollected: boolean;
  host: MysqlHostCandidate | null;
  hostHref: string;
  cpuPercent: number | null;
  memPercent: number | null;
  alertsOpen: boolean;
  alertEvents: HostAlertRailEvent[];
  onOpenAlerts: () => void;
  onFocusAlert: (alertId: string) => void;
  onOpenFocus: (card: MysqlFocusCard) => void;
}

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
  loading,
  statementsCollected,
  host: linkedHost,
  hostHref,
  cpuPercent,
  memPercent,
  alertsOpen,
  alertEvents,
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
  const role = useMemo(() => readMysqlRoleBlock(metricMap), [metricMap]);

  return (
    <>
      <ProSectionTitle>健康概览</ProSectionTitle>
      {cards.length > 0 ? <KpiTileRow items={cards} /> : null}
      {!loading && cards.length === 0 ? (
        <div className="text-[13px] text-[var(--color-text-3)]">当前窗口没有可展示的实例指标</div>
      ) : null}

      <ProSectionTitle>所属主机</ProSectionTitle>
      <MysqlHostRail
        host={linkedHost}
        href={hostHref}
        cpuPercent={cpuPercent}
        memPercent={memPercent}
      />

      <ProSectionTitle>事件</ProSectionTitle>
      <EventsRail events={alertEvents} onFocusAlert={onFocusAlert} />

      {focus.length > 0 ? (
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
                    <div className={host.shortcutMain}>{card.value}</div>
                    {card.delta ? (
                      <div className={host.shortcutValue} style={card.deltaTone ? { color: card.deltaTone } : undefined}>
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

      {trends.row.length > 0 ? (
        <>
          <ProSectionTitle>实例趋势</ProSectionTitle>
          <div className={host.chartGrid4}>
            {trends.row.map((chart) => (
              <ThinTimeSeries
                key={chart.key}
                title={chart.title}
                unit={chart.unit}
                data={chart.data}
                legends={chart.legends}
                reading={chart.reading}
                loading={loading}
              />
            ))}
          </div>
          {trends.extra.length > 0 ? (
            <div className={host.chartGrid2}>
              {trends.extra.map((chart) => (
                <ThinTimeSeries
                  key={chart.key}
                  title={chart.title}
                  unit={chart.unit}
                  data={chart.data}
                  legends={chart.legends}
                  reading={chart.reading}
                  loading={loading}
                />
              ))}
            </div>
          ) : null}
        </>
      ) : null}

      <MysqlRoleBlock block={role} />
    </>
  );
}
