'use client';

import React, { useMemo } from 'react';
import {
  EVENT_RAIL_HINT_LINES,
  KpiTileRow,
  ProInfoHint,
  ProSection,
  type KpiTileModel
} from '../../host/layered/pro-chrome';
import EventsRail, { type HostAlertRailEvent } from '../../host/layered/events-rail';
import type { PreparedSummaryCard } from '../../common/simple-dashboard-core';
import { useDashboardText } from '../../../shared/utils/content-i18n';
import { redisCategoryText, type RedisCategoryCopyKey } from './redis-copy';
import { redisMemoryLimitUnset, type RedisMetricMap } from './series';
import FocusPane, { type RedisTopicTab } from './focus-pane';
import { CompactTrends } from './topic-panes';

interface OverviewPaneProps {
  summaryCards: PreparedSummaryCard[];
  loading: boolean;
  metricMap: RedisMetricMap;
  pendingMetricNames: ReadonlySet<string>;
  alertEvents: HostAlertRailEvent[];
  eventsLoading: boolean;
  onFocusAlert: (alertId: string) => void;
  onOpen: (tab: RedisTopicTab) => void;
}

const headline = (main: PreparedSummaryCard['mainValue']) => (
  main.unit ? `${main.value}${main.unit}` : main.value
);

/** 概览主序：五 KPI、事件、重点关注 2×2、紧凑趋势。诊断 Tab 不再复制这排 KPI。 */
export default function OverviewPane({
  summaryCards,
  loading,
  metricMap,
  pendingMetricNames,
  alertEvents,
  eventsLoading,
  onFocusAlert,
  onOpen
}: OverviewPaneProps) {
  const { t, dt } = useDashboardText();
  const text = (key: RedisCategoryCopyKey) => redisCategoryText(t, key);
  const limitUnset = redisMemoryLimitUnset(metricMap);
  const cards = useMemo<KpiTileModel[]>(() => (
    summaryCards.map((summary) => {
      const unsetUtilization = limitUnset && summary.card.metric === 'redis_memory_utilization';
      const empty = unsetUtilization || summary.mainValue.value === '--';
      return {
        key: summary.card.metric,
        label: dt(summary.card.title),
        value: unsetUtilization ? '--' : headline(summary.mainValue),
        tone: empty ? undefined : (summary.valueColor ?? summary.card.color),
        subtitle: unsetUtilization
          ? text('memoryLimitUnset')
          : summary.card.isUptimeCard && summary.uptimeState
            ? dt(summary.uptimeState.label)
            : undefined
      };
    })
  ), [dt, limitUnset, summaryCards, t]);

  return (
    <div data-redis-pane="overview" className="contents">
      <ProSection title={text('healthOverview')}>
        <KpiTileRow items={cards} loading={loading} columns={5} />
      </ProSection>
      <ProSection
        title={text('events')}
        hint={<ProInfoHint kind="events" lines={EVENT_RAIL_HINT_LINES} />}
      >
        <EventsRail events={alertEvents} loading={eventsLoading} onFocusAlert={onFocusAlert} />
      </ProSection>
      <FocusPane metricMap={metricMap} pending={pendingMetricNames} onOpen={onOpen} />
      <ProSection title={text('overviewTrends')}>
        <CompactTrends metricMap={metricMap} pending={pendingMetricNames} />
      </ProSection>
    </div>
  );
}
