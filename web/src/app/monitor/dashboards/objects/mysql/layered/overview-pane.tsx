'use client';

import React, { useCallback, useMemo } from 'react';
import {
  EVENT_RAIL_HINT_LINES,
  KpiTileRow,
  ProDashLoading,
  ProFocusCard,
  ProInfoHint,
  ProSection,
  ThinTimeSeries,
  proChromeClass,
  type KpiTileModel
} from '../../host/layered/pro-chrome';
import EventsRail, { type HostAlertRailEvent } from '../../host/layered/events-rail';
import { HOST_PALETTE, HOST_SERIES_COLOR } from '../../host/config';
import { primaryChartSeries } from '../../host/layered/readings';
import FocusShortcutTitle from '../../host/layered/focus-shortcut-title';
import { describeFocusAxis, seriesSampleValues } from '../../host/layered/focus-axis';
import { useProTimeWindow } from '../../host/layered/pro-time-window';
import { clipChartDataToWindow } from '../../../shared/utils/pro-chart-window';
import { mergeChartSeries } from '../../../shared/utils/chart-data';
import {
  buildMysqlFocusCards,
  buildMysqlOverviewKpis,
  mysqlHealthKpiJump,
  type MysqlFocusCard,
  type MysqlFocusSpark,
  type MysqlIaTab,
  type MysqlOverviewReadings
} from './ia';
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
  alertsOpen: boolean;
  alertEvents: HostAlertRailEvent[];
  eventsLoading: boolean;
  slowAlertActive: boolean;
  instanceName: string;
  onOpenAlerts: () => void;
  onFocusAlert: (alertId: string) => void;
  onOpenFocus: (card: MysqlFocusCard) => void;
  onOpenHealthKpi: (tab: MysqlIaTab, anchor: string) => void;
}

const MYSQL_LOADING_KPIS: KpiTileModel[] = ['connections', 'qps', 'slow', 'replication', 'uptime', 'alerts'].map((key) => ({
  key,
  label: key,
  value: ''
}));

const FOCUS_LOADING: Array<{
  title: MysqlCategoryCopyKey;
  unit: 'counts' | 'percent' | 'cps';
}> = [
  { title: 'focusActive', unit: 'counts' },
  { title: 'focusBuffer', unit: 'percent' },
  { title: 'focusRowLock', unit: 'cps' },
  { title: 'focusTmpDisk', unit: 'percent' }
];

const SPARK_METRIC: Record<MysqlFocusSpark, Array<{
  name: string;
  unit: 'counts' | 'cps' | 'percent';
  color: string;
  label: MysqlCategoryCopyKey;
}>> = {
  active: [{
    name: 'mysql_threads_running',
    unit: 'counts',
    color: HOST_SERIES_COLOR.load1,
    label: 'focusActive'
  }],
  bufferHit: [{
    name: 'mysql_buffer_pool_hit_ratio',
    unit: 'percent',
    color: HOST_SERIES_COLOR.cpu,
    label: 'focusBuffer'
  }],
  rowLock: [{
    name: 'mysql_innodb_row_lock_waits_rate',
    unit: 'cps',
    color: HOST_PALETTE.orange,
    label: 'focusRowLock'
  }],
  tmpDisk: [{
    name: 'mysql_tmp_disk_table_ratio',
    unit: 'percent',
    color: HOST_SERIES_COLOR.load5,
    label: 'focusTmpDisk'
  }]
};

export default function OverviewPane({
  readings,
  metricMap,
  previousMetricMap,
  pendingMetricNames,
  alertsOpen,
  alertEvents,
  eventsLoading,
  slowAlertActive,
  instanceName,
  onOpenAlerts,
  onFocusAlert,
  onOpenFocus,
  onOpenHealthKpi
}: OverviewPaneProps) {
  const { t } = useDashboardText();
  const text = useCallback((key: MysqlCategoryCopyKey, values?: Record<string, string | number>) => (
    mysqlCategoryText(t, key, values)
  ), [t]);
  const cards = useMemo<KpiTileModel[]>(() => (
    buildMysqlOverviewKpis(readings, metricMap, text, slowAlertActive, {
      instanceName
    }).map((card) => ({
      key: card.key,
      label: card.label,
      value: card.value,
      subtitle: card.subtitle,
      tone: card.tone,
      alertLevel: card.alertLevel,
      onActivate: card.key === 'alerts'
        ? onOpenAlerts
        : (() => {
          const jump = mysqlHealthKpiJump(card.key);
          return jump ? () => onOpenHealthKpi(jump.tab, jump.anchor) : undefined;
        })(),
      expanded: card.key === 'alerts' ? alertsOpen : undefined
    }))
  ), [
    alertsOpen,
    instanceName,
    metricMap,
    onOpenAlerts,
    onOpenHealthKpi,
    readings,
    slowAlertActive,
    text
  ]);
  const focus = useMemo(
    () => buildMysqlFocusCards(metricMap, previousMetricMap, text),
    [metricMap, previousMetricMap, text]
  );
  const healthLoading = blocksUntilReady(MYSQL_HEALTH_METRICS, pendingMetricNames);
  const focusLoading = blocksUntilReady(MYSQL_FOCUS_METRICS, pendingMetricNames);
  const proTime = useProTimeWindow();
  const chartWindow = proTime?.window ?? null;
  const focusPath = text('focusPath');

  return (
    <>
      <ProSection title={text('healthOverview')}>
        {healthLoading ? (
          <KpiTileRow loading items={MYSQL_LOADING_KPIS} />
        ) : (
          <KpiTileRow items={cards} />
        )}
      </ProSection>

      <ProSection
        title={text('events')}
        hint={<ProInfoHint kind="events" lines={EVENT_RAIL_HINT_LINES} />}
      >
        <EventsRail events={alertEvents} loading={eventsLoading} onFocusAlert={onFocusAlert} />
      </ProSection>

      <ProSection title={text('focus')} hint={<ProInfoHint kind="focus" text={focusPath} />}>
        {focusLoading ? (
          <div className={proChromeClass.shortcutGrid}>
            {FOCUS_LOADING.map((item) => (
              <ProFocusCard key={item.title}>
                <div className={proChromeClass.shortcutCopy}>
                  <FocusShortcutTitle
                    label={text(item.title)}
                    unit={describeFocusAxis(item.unit, []).unitLabel}
                  />
                  <ProDashLoading size="small" />
                </div>
                <div className={proChromeClass.focusChart} />
              </ProFocusCard>
            ))}
          </div>
        ) : (
          <div className={proChromeClass.shortcutGrid}>
            {focus.map((card) => {
              const sparks = card.spark ? SPARK_METRIC[card.spark] : [];
              const plotted = mergeChartSeries(sparks.flatMap((spark) => {
                const series = metricMap[spark.name];
                const points = series?.loadState === 'success' ? primaryChartSeries(series.viewData) : [];
                return points.length ? [{ key: spark.name, label: text(spark.label), data: points }] : [];
              }));
              const axisUnit = describeFocusAxis(
                SPARK_METRIC[card.key][0].unit,
                seriesSampleValues(clipChartDataToWindow(plotted, chartWindow))
              ).unitLabel;
              return (
                <ProFocusCard key={card.key}>
                  <div className={proChromeClass.shortcutCopy}>
                    <FocusShortcutTitle label={card.label} unit={axisUnit} />
                    <div className={proChromeClass.shortcutValue} style={card.tone ? { color: card.tone } : undefined}>
                      {card.value}
                    </div>
                    {card.delta ? (
                      <div className={proChromeClass.shortcutSub} style={card.deltaTone ? { color: card.deltaTone } : undefined}>
                        {card.delta}
                      </div>
                    ) : card.subtitle ? (
                      <div className={proChromeClass.shortcutSub}>{card.subtitle}</div>
                    ) : null}
                    <button type="button" className={proChromeClass.jumpBtn} onClick={() => onOpenFocus(card)}>
                      {card.hint}
                    </button>
                  </div>
                  {plotted.length > 0 ? (
                    <ThinTimeSeries
                      bare
                      numericAxis
                      className={proChromeClass.focusChart}
                      title=""
                      unit={sparks[0]?.unit}
                      data={plotted}
                      legends={sparks.map((spark) => ({ label: text(spark.label), color: spark.color }))}
                    />
                  ) : (
                    <div className={proChromeClass.focusChart} />
                  )}
                </ProFocusCard>
              );
            })}
          </div>
        )}
      </ProSection>
    </>
  );
}
