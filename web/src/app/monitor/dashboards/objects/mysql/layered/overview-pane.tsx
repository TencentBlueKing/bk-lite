'use client';

import React, { useCallback, useMemo } from 'react';
import { ProEventsSectionTitle } from '../../host/layered/alert-event-hint';
import { KpiTileRow, ProDashLoading, ProSectionTitle, ThinTimeSeries, type KpiTileModel } from '../../host/layered/pro-chrome';
import EventsRail, { type HostAlertRailEvent } from '../../host/layered/events-rail';
import { HOST_PALETTE, HOST_SERIES_COLOR } from '../../host/config';
import { primaryChartSeries } from '../../host/layered/readings';
import FocusShortcutTitle from '../../host/layered/focus-shortcut-title';
import { describeFocusAxis, seriesSampleValues } from '../../host/layered/focus-axis';
import { useProTimeWindow } from '../../host/layered/pro-time-window';
import { clipChartDataToWindow } from '../../../shared/utils/pro-chart-window';
import { mergeChartSeries } from '../../../shared/utils/chart-data';
import classic from '../../host/index.module.scss';
import host from '../../host/layered/layered.module.scss';
import pro from './pro.module.scss';
import {
  buildMysqlFocusCards,
  buildMysqlOverviewKpis,
  type MysqlFocusCard,
  type MysqlFocusSpark,
  type MysqlHostCandidate,
  type MysqlOverviewReadings
} from './ia';
import { MysqlHostNote } from './instance-identity';
import { mysqlCategoryText, type MysqlCategoryCopyKey } from './mysql-copy';
import {
  MYSQL_FOCUS_METRICS,
  MYSQL_HEALTH_METRICS,
  blocksUntilReady
} from './section-loading';
import type { MetricSeries as MysqlMetricSeries } from '../types';
import { useDashboardText } from '../../../shared/utils/content-i18n';

interface OverviewPaneProps {
  readings: MysqlOverviewReadings;
  metricMap: Record<string, MysqlMetricSeries | undefined>;
  previousMetricMap: Record<string, MysqlMetricSeries | undefined>;
  pendingMetricNames: ReadonlySet<string>;
  host: MysqlHostCandidate | null;
  hostHref: string;
  hostLoading: boolean;
  alertsOpen: boolean;
  alertEvents: HostAlertRailEvent[];
  eventsLoading: boolean;
  onOpenAlerts: () => void;
  onFocusAlert: (alertId: string) => void;
  onOpenFocus: (card: MysqlFocusCard) => void;
  onOpenReplication: () => void;
}

const MYSQL_LOADING_KPIS: KpiTileModel[] = ['connections', 'qps', 'slow', 'replication', 'uptime', 'alerts'].map((key) => ({
  key,
  label: key,
  value: ''
}));

const FOCUS_LOADING: MysqlCategoryCopyKey[] = [
  'focusLockWait',
  'focusAborted',
  'focusTmpDisk',
  'focusReplLag'
];

const SPARK_METRIC: Record<MysqlFocusSpark, Array<{
  name: string;
  unit: 'counts' | 'cps' | 'percent' | 's';
  color: string;
  label: MysqlCategoryCopyKey;
}>> = {
  lockWait: [{
    name: 'mysql_process_list_threads_waiting_for_lock',
    unit: 'counts',
    color: HOST_SERIES_COLOR.load1,
    label: 'focusLockWait'
  }],
  aborted: [
    {
      name: 'mysql_aborted_connects_rate',
      unit: 'cps',
      color: HOST_PALETTE.rose,
      label: 'abortedConnects'
    },
    {
      name: 'mysql_aborted_clients_rate',
      unit: 'cps',
      color: HOST_PALETTE.orange,
      label: 'abortedClients'
    }
  ],
  tmpDisk: [{
    name: 'mysql_tmp_disk_table_ratio',
    unit: 'percent',
    color: HOST_PALETTE.rose,
    label: 'focusTmpDisk'
  }],
  replLag: [{
    name: 'mysql_slave_seconds_behind_master',
    unit: 's',
    color: HOST_SERIES_COLOR.memUsed,
    label: 'focusReplLag'
  }],
  tableLock: [{
    name: 'mysql_table_locks_waited_rate',
    unit: 'cps',
    color: HOST_PALETTE.orange,
    label: 'focusTableLock'
  }]
};

export default function OverviewPane({
  readings,
  metricMap,
  previousMetricMap,
  pendingMetricNames,
  host: linkedHost,
  hostHref,
  hostLoading,
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
    buildMysqlOverviewKpis(readings, metricMap, text).map((card) => ({
      key: card.key,
      label: card.label,
      value: card.value,
      subtitle: card.subtitle,
      tone: card.tone,
      alertLevel: card.alertLevel,
      onActivate: card.key === 'alerts'
        ? onOpenAlerts
        : (card.key === 'replication' && card.clickable ? onOpenReplication : undefined),
      expanded: card.key === 'alerts' ? alertsOpen : undefined
    }))
  ), [alertsOpen, metricMap, onOpenAlerts, onOpenReplication, readings, text]);
  const focus = useMemo(
    () => buildMysqlFocusCards(metricMap, previousMetricMap, text),
    [metricMap, previousMetricMap, text]
  );
  const healthLoading = blocksUntilReady(MYSQL_HEALTH_METRICS, pendingMetricNames);
  const focusLoading = blocksUntilReady(MYSQL_FOCUS_METRICS, pendingMetricNames);
  const proTime = useProTimeWindow();
  const chartWindow = proTime?.window ?? null;

  return (
    <>
      <div className={pro.healthBlock}>
        <ProSectionTitle>{text('healthOverview')}</ProSectionTitle>
        <MysqlHostNote
          host={linkedHost}
          href={hostHref}
          hostLoading={hostLoading}
        />
      </div>
      {healthLoading ? (
        <KpiTileRow loading items={MYSQL_LOADING_KPIS} />
      ) : (
        <KpiTileRow items={cards} />
      )}

      <ProEventsSectionTitle title={text('events')} />
      <EventsRail events={alertEvents} loading={eventsLoading} onFocusAlert={onFocusAlert} />

      {focusLoading ? (
        <>
          <ProSectionTitle>{text('focus')}</ProSectionTitle>
          <div className={host.shortcutGrid}>
            {FOCUS_LOADING.map((titleKey) => (
              <div key={titleKey} className={`${classic.panel} ${host.shortcutCard}`}>
                <div className={host.shortcutCopy}>
                  <FocusShortcutTitle label={text(titleKey)} unit="" />
                  <ProDashLoading size="small" />
                </div>
                <div className={host.focusChart} />
              </div>
            ))}
          </div>
        </>
      ) : (
        <>
          <ProSectionTitle>{text('focus')}</ProSectionTitle>
          <div className={host.shortcutGrid}>
            {focus.map((card) => {
              const sparks = card.spark ? SPARK_METRIC[card.spark] : [];
              const plotted = mergeChartSeries(sparks.flatMap((spark) => {
                const series = metricMap[spark.name];
                const points = series?.loadState === 'success' ? primaryChartSeries(series.viewData) : [];
                return points.length ? [{ key: spark.name, label: text(spark.label), data: points }] : [];
              }));
              const axisUnit = sparks[0]
                ? describeFocusAxis(
                  sparks[0].unit,
                  seriesSampleValues(clipChartDataToWindow(plotted, chartWindow))
                ).unitLabel
                : '';
              return (
                <div key={card.key} className={`${classic.panel} ${host.shortcutCard}`}>
                  <div className={host.shortcutCopy}>
                    <FocusShortcutTitle label={card.label} unit={axisUnit} />
                    <div className={host.shortcutValue} style={card.tone ? { color: card.tone } : undefined}>
                      {card.value}
                    </div>
                    {card.delta ? (
                      <div className={host.shortcutSub} style={card.deltaTone ? { color: card.deltaTone } : undefined}>
                        {card.delta}
                      </div>
                    ) : card.subtitle ? (
                      <div className={host.shortcutSub}>{card.subtitle}</div>
                    ) : null}
                    <button type="button" className={host.jumpBtn} onClick={() => onOpenFocus(card)}>
                      {card.hint}
                    </button>
                  </div>
                  {plotted.length > 0 ? (
                    <ThinTimeSeries
                      bare
                      numericAxis
                      className={host.focusChart}
                      title=""
                      unit={sparks[0]?.unit}
                      data={plotted}
                      legends={sparks.map((spark) => ({ label: text(spark.label), color: spark.color }))}
                    />
                  ) : (
                    <div className={host.focusChart} />
                  )}
                </div>
              );
            })}
          </div>
        </>
      )}
    </>
  );
}
