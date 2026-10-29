'use client';

import React, { useMemo } from 'react';
import {
  EVENT_RAIL_HINT_LINES,
  ProInfoHint,
  ProSection
} from '../../host/layered/pro-chrome';
import { RedisKpiTileRow, type RedisKpiTile } from './redis-kpi-row';
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

/** 概览五卡的空态。瞬时命令速率不在这排，那句「窗口内暂无采样」不能套到这里。 */
const OVERVIEW_EMPTY: Record<string, { empty: string; value: RedisCategoryCopyKey; detail: RedisCategoryCopyKey }> = {
  redis_uptime: { empty: 'uptime', value: 'uptimeEmpty', detail: 'uptimeEmptyTip' },
  redis_memory_utilization: { empty: 'memory-usage', value: 'memoryUsageEmpty', detail: 'memoryUsageEmptyTip' },
  redis_keyspace_hitrate: { empty: 'hit-rate', value: 'hitRateEmpty', detail: 'hitRateEmptyTip' },
  redis_evicted_keys_rate: { empty: 'eviction', value: 'evictionEmpty', detail: 'evictionEmptyTip' },
  redis_clients: { empty: 'clients', value: 'clientsEmpty', detail: 'clientsEmptyTip' }
};

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
  const cards = useMemo<RedisKpiTile[]>(() => (
    summaryCards.map((summary) => {
      const metric = summary.card.metric;
      const label = dt(summary.card.title);
      if (limitUnset && metric === 'redis_memory_utilization') {
        return {
          key: metric,
          label,
          value: text('memoryLimitUnset'),
          detail: text('memoryLimitUnsetTip'),
          prose: true,
          empty: 'memory-limit'
        };
      }
      const empty = summary.mainValue.value === '--';
      if (empty) {
        const known = OVERVIEW_EMPTY[metric] ?? {
          empty: 'reading',
          value: 'readingEmpty' as const,
          detail: 'readingEmptyTip' as const
        };
        return {
          key: metric,
          label,
          value: text(known.value),
          detail: text(known.detail),
          prose: true,
          empty: known.empty
        };
      }
      const restart = summary.card.isUptimeCard && summary.uptimeState?.tone === 'warning'
        ? dt(summary.uptimeState.label)
        : undefined;
      return {
        key: metric,
        label,
        value: headline(summary.mainValue),
        tone: summary.valueColor ?? summary.card.color,
        subtitle: restart
      };
    })
  ), [dt, limitUnset, summaryCards, t]);

  return (
    <div data-redis-pane="overview" className="contents">
      <ProSection title={text('healthOverview')}>
        <RedisKpiTileRow items={cards} loading={loading} columns={5} />
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
