'use client';

import React, { useCallback, useMemo } from 'react';
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
  buildMysqlReplicationHealthCards,
  readMysqlProHeader,
  type MysqlFocusCard,
  type MysqlHostCandidate,
  type MysqlOverviewReadings
} from './ia';
import MysqlInstanceSummaryCard from './instance-summary-card';
import { mysqlCategoryText, type MysqlCategoryCopyKey } from './mysql-copy';
import {
  MYSQL_FOCUS_METRICS,
  MYSQL_HEADER_METRICS,
  MYSQL_HEALTH_METRICS,
  MYSQL_ROLE_METRICS,
  blocksUntilReady
} from './section-loading';
import type { MetricSeries as MysqlMetricSeries } from '../types';
import { useDashboardText } from '../../../shared/utils/content-i18n';

interface OverviewPaneProps {
  readings: MysqlOverviewReadings;
  previous: Pick<MysqlOverviewReadings, 'slowPerSecond'>;
  metricMap: Record<string, MysqlMetricSeries | undefined>;
  pendingMetricNames: ReadonlySet<string>;
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
  onOpenReplication: () => void;
}

const MYSQL_LOADING_KPIS: KpiTileModel[] = ['connections', 'qps', 'slow', 'buffer', 'uptime', 'alerts'].map((key) => ({
  key,
  label: key,
  value: ''
}));

const FOCUS_LOADING: MysqlCategoryCopyKey[] = ['focusSlow'];

const SPARK_METRIC: Record<NonNullable<MysqlFocusCard['spark']>, { name: string; unit: 'counts' | 'cps' | 'percent'; color: string }> = {
  slow: { name: 'mysql_slow_queries_rate', unit: 'cps', color: HOST_SERIES_COLOR.load1 }
};

const REPL_LOADING_KPIS: KpiTileModel[] = ['lag', 'io', 'sql'].map((key) => ({
  key,
  label: key,
  value: ''
}));

export default function OverviewPane({
  readings,
  previous,
  metricMap,
  pendingMetricNames,
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
  onOpenFocus,
  onOpenReplication
}: OverviewPaneProps) {
  const { t } = useDashboardText();
  const text = useCallback((key: MysqlCategoryCopyKey, values?: Record<string, string | number>) => (
    mysqlCategoryText(t, key, values)
  ), [t]);
  const cards = useMemo<KpiTileModel[]>(() => (
    buildMysqlOverviewKpis(readings, text).map((card) => ({
      key: card.key,
      label: card.label,
      value: card.value,
      subtitle: card.subtitle,
      tone: card.tone,
      onActivate: card.key === 'alerts' ? onOpenAlerts : undefined,
      expanded: card.key === 'alerts' ? alertsOpen : undefined
    }))
  ), [alertsOpen, onOpenAlerts, readings, text]);
  const focus = useMemo(
    () => buildMysqlFocusCards(readings, previous, text),
    [previous, readings, text]
  );
  const healthLoading = blocksUntilReady(MYSQL_HEALTH_METRICS, pendingMetricNames);
  const replicationLoading = blocksUntilReady(MYSQL_ROLE_METRICS, pendingMetricNames);
  const replicationHealth = useMemo(
    () => (replicationLoading ? [] : buildMysqlReplicationHealthCards(metricMap, text)),
    [metricMap, replicationLoading, text]
  );
  const focusLoading = blocksUntilReady(MYSQL_FOCUS_METRICS, pendingMetricNames);
  const headerPending = blocksUntilReady(MYSQL_HEADER_METRICS, pendingMetricNames);
  const header = headerPending ? null : readMysqlProHeader(metricMap);
  const proTime = useProTimeWindow();
  const chartWindow = proTime?.window ?? null;

  return (
    <>
      <MysqlInstanceSummaryCard
        header={header}
        headerPending={headerPending}
        host={linkedHost}
        href={hostHref}
        cpuPercent={cpuPercent}
        memPercent={memPercent}
        hostLoading={hostLoading}
      />
      <ProSectionTitle>{text('healthOverview')}</ProSectionTitle>
      {healthLoading ? (
        <KpiTileRow loading items={MYSQL_LOADING_KPIS} />
      ) : (
        <KpiTileRow items={cards} />
      )}

      {replicationLoading || replicationHealth.length > 0 ? (
        <>
          <ProSectionTitle>{text('replicationHealth')}</ProSectionTitle>
          {replicationLoading ? (
            <KpiTileRow loading items={REPL_LOADING_KPIS} />
          ) : (
            <KpiTileRow
              items={replicationHealth.map((card) => ({
                key: card.key,
                label: card.label,
                value: card.value,
                tone: card.tone,
                onActivate: onOpenReplication
              }))}
            />
          )}
        </>
      ) : null}

      <ProEventsSectionTitle title={text('events')} />
      <EventsRail events={alertEvents} loading={eventsLoading} onFocusAlert={onFocusAlert} />

      {focusLoading ? (
        <>
          <ProSectionTitle>{text('focus')}</ProSectionTitle>
          <div className={host.shortcutGrid}>
            {FOCUS_LOADING.map((titleKey) => (
              <ThinTimeSeries
                key={titleKey}
                title={text(titleKey)}
                loading
                data={[]}
                legends={[]}
              />
            ))}
          </div>
        </>
      ) : focus.length > 0 ? (
        <>
          <ProSectionTitle>{text('focus')}</ProSectionTitle>
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
