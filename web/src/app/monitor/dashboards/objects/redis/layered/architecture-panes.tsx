'use client';

import { useMemo } from 'react';
import type { ReactNode } from 'react';
import { GrayTabEmptyState, ProDashLoading, ProSection, ThinTimeSeries, proChromeClass } from '../../host/layered/pro-chrome';
import chart from '../../host/layered/layered.module.scss';
import { useDashboardText } from '../../../shared/utils/content-i18n';
import { formatMetricValue } from '../../../shared/utils/format';
import type { ChartData } from '@/app/monitor/types';
import { REDIS_PALETTE } from '../config';
import styles from '../index.module.scss';
import {
  backlogFill,
  flagOn,
  linkTone,
  type ReplicationTabMode
} from './architecture-state';
import { redisCategoryText, type RedisCategoryCopyKey } from './redis-copy';
import { RedisHint } from './redis-hint';
import {
  redisDisplay,
  redisLatest,
  redisPoints,
  replicationOffsetLag,
  type RedisMetricMap
} from './series';
import RedisTrendChart, { type RedisTrendSpec } from './trend-chart';

const BACKLOG_NAMES = [
  'redis_repl_backlog_active',
  'redis_repl_backlog_size',
  'redis_repl_backlog_histlen',
  'redis_mem_replication_backlog'
] as const;

const OFFSET_SERIES = [
  { name: 'redis_master_repl_offset', labelKey: 'seriesMasterOffset', color: REDIS_PALETTE.cyan },
  { name: 'redis_slave_repl_offset', labelKey: 'seriesSlaveOffset', color: REDIS_PALETTE.emerald }
] as const;

/** 复制状态四项跟主机 KPI 同一套壳，四列铺满、顶对齐、留白一致。 */
function ReplicaStatusGrid({ children }: { children: ReactNode }) {
  return (
    <div
      className={proChromeClass.kpiGrid}
      style={{ gridTemplateColumns: 'repeat(4, minmax(0, 1fr))' }}
      data-redis-status-row="kpi"
    >
      {children}
    </div>
  );
}

/** 积压三条折线铺满一行。趋势卡边框跟格子走。 */
const backlogTrendRow = `${chart.chartGrid3} items-stretch`;
const trendCell = 'flex h-full min-w-0 flex-col [&>section]:h-full';

function useRedisText() {
  const { t } = useDashboardText();
  return (key: RedisCategoryCopyKey) => redisCategoryText(t, key);
}

function FeatureHead({
  title,
  hint,
  lines,
  kind
}: {
  title: string;
  hint?: string;
  lines?: readonly string[];
  kind?: string;
}) {
  const tipLines = lines?.length ? lines : hint ? [hint] : [];
  const tip = tipLines.length ? (
    <RedisHint kind={kind || 'redis-arch'} lines={tipLines} />
  ) : null;
  return (
    <div className={chart.chartHead}>
      <div className={chart.chartTitleGroup}>
        <div className={chart.chartTitleBlock}>
          <div className={chart.chartTitle}>
            {tip ? (
              <span className="inline-flex items-center gap-1">
                {title}
                {tip}
              </span>
            ) : title}
          </div>
        </div>
      </div>
    </div>
  );
}

function QuietReading({ copy }: { copy: string }) {
  return (
    <p className="m-0 mt-1 text-[13px] font-medium leading-5 text-[var(--color-text-2)]" data-redis-empty="reading">
      {copy}
    </p>
  );
}

function Pane({ pane, children }: { pane: string; children: ReactNode }) {
  return (
    <div data-redis-pane={pane} className="contents">
      {children}
    </div>
  );
}

function LoadingCard({ title, feature }: { title: string; feature: string }) {
  return (
    <section className={`${styles.panel} h-full`} data-redis-feature={feature} data-redis-state="loading">
      <FeatureHead title={title} />
      <ProDashLoading />
    </section>
  );
}

const SLAVES_TREND: RedisTrendSpec = {
  titleKey: 'cardConnectedSlaves',
  hintKey: 'connectedSlavesHint',
  emptyKey: 'slavesEmpty',
  unit: 'counts',
  series: [{
    name: 'redis_connected_slaves',
    labelKey: 'cardConnectedSlaves',
    color: REDIS_PALETTE.blue
  }]
};

function ConnectedSlavesCard({
  metricMap,
  pending
}: {
  metricMap: RedisMetricMap;
  pending: ReadonlySet<string>;
}) {
  const latest = redisLatest(metricMap, 'redis_connected_slaves');
  return (
    <div
      className="flex h-full min-w-0 flex-col [&>section]:h-full"
      data-redis-feature="connected-slaves"
      data-redis-spark={latest == null ? 'empty' : 'connected-slaves'}
    >
      <RedisTrendChart spec={SLAVES_TREND} metricMap={metricMap} pending={pending} />
    </div>
  );
}

const BACKLOG_USED: RedisTrendSpec = {
  titleKey: 'backlogUsed',
  emptyKey: 'backlogUnread',
  unit: 'bytes',
  series: [{
    name: 'redis_repl_backlog_histlen',
    labelKey: 'backlogUsed',
    color: REDIS_PALETTE.blue
  }]
};

const BACKLOG_SIZE: RedisTrendSpec = {
  titleKey: 'backlogCapacity',
  emptyKey: 'backlogUnread',
  unit: 'bytes',
  series: [{
    name: 'redis_repl_backlog_size',
    labelKey: 'backlogCapacity',
    color: REDIS_PALETTE.cyan
  }]
};

/** 占比 = 同一时刻已用长度 ÷ 积压大小。只配对真实采样，不另造采集指标。 */
function backlogSharePoints(metricMap: RedisMetricMap): ChartData[] {
  const limitAt = new Map<number, number>();
  redisPoints(metricMap, 'redis_repl_backlog_size').forEach((point) => {
    const limit = point.value1;
    const time = Number(point.time);
    if (typeof limit === 'number' && limit > 0 && Number.isFinite(time)) limitAt.set(time, limit);
  });
  const points: ChartData[] = [];
  redisPoints(metricMap, 'redis_repl_backlog_histlen').forEach((point) => {
    const time = Number(point.time);
    const written = point.value1;
    if (typeof written !== 'number' || !Number.isFinite(time)) return;
    const ratio = backlogFill(written, limitAt.get(time));
    if (ratio == null) return;
    points.push({ time, value1: ratio });
  });
  points.sort((left, right) => Number(left.time) - Number(right.time));
  return points;
}

function BacklogShareChart({
  metricMap,
  pending
}: {
  metricMap: RedisMetricMap;
  pending: ReadonlySet<string>;
}) {
  const text = useRedisText();
  const points = useMemo(() => backlogSharePoints(metricMap), [metricMap]);
  const loading = points.length === 0 && (
    pending.has('redis_repl_backlog_histlen') || pending.has('redis_repl_backlog_size')
  );
  return (
    <div className={trendCell} data-redis-backlog-card="share">
      <ThinTimeSeries
        title={text('backlogShare')}
        unit="percent"
        data={points}
        legends={[{ label: text('backlogShare'), color: REDIS_PALETTE.amber }]}
        loading={loading}
        emptyText={text('backlogUnread')}
        hintNode={(
          <RedisHint
            kind="redis-backlog-share"
            lines={[text('backlogPctExplain')]}
          />
        )}
      />
    </div>
  );
}

function BacklogTrends({
  metricMap,
  pending
}: {
  metricMap: RedisMetricMap;
  pending: ReadonlySet<string>;
}) {
  const text = useRedisText();
  return (
    <div className="min-w-0" data-redis-backlog-layout="trend">
      <div className={backlogTrendRow}>
        <div className={trendCell} data-redis-backlog-card="used">
          <RedisTrendChart
            spec={BACKLOG_USED}
            metricMap={metricMap}
            pending={pending}
            hint={<RedisHint kind="redis-backlog-used" lines={[text('backlogWritten')]} />}
          />
        </div>
        <div className={trendCell} data-redis-backlog-card="size">
          <RedisTrendChart
            spec={BACKLOG_SIZE}
            metricMap={metricMap}
            pending={pending}
            hint={<RedisHint kind="redis-backlog-size" lines={[text('backlogLimitExplain')]} />}
          />
        </div>
        <BacklogShareChart metricMap={metricMap} pending={pending} />
      </div>
    </div>
  );
}

function countText(value: number) {
  const formatted = formatMetricValue(value, 'counts');
  return formatted.unit ? `${formatted.value}${formatted.unit}` : formatted.value;
}

function StatusTile({
  feature,
  label,
  hintKind,
  lines,
  locked,
  value,
  tone,
  empty,
  accent,
  loading,
  dataAttrs
}: {
  feature: string;
  label: string;
  hintKind: string;
  lines?: readonly string[];
  locked?: readonly string[];
  value?: string;
  tone?: string;
  empty?: string;
  /** 主从链接的细色条。只在有明确通断时上色，安静态不加假色块。 */
  accent?: string;
  loading?: boolean;
  dataAttrs?: Record<string, string | undefined>;
}) {
  return (
    <div
      className={loading
        ? `${proChromeClass.kpiCard} ${proChromeClass.kpiCardLoading}`
        : proChromeClass.kpiCard}
      style={accent ? { borderLeftWidth: 3, borderLeftColor: accent } : undefined}
      data-redis-feature={feature}
      {...dataAttrs}
    >
      {loading ? <ProDashLoading size="small" layout="inline" /> : (
        <>
          <div className={`${proChromeClass.kpiLabel} inline-flex max-w-full items-center gap-1 !overflow-visible`}>
            <span className="min-w-0 truncate">{label}</span>
            {lines?.length || locked?.length ? (
              <RedisHint kind={hintKind} lines={lines} locked={locked} />
            ) : null}
          </div>
          {empty ? <QuietReading copy={empty} /> : (
            <div className={proChromeClass.kpiValue} style={tone ? { color: tone } : undefined}>
              {value}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function ReplicaStatusRow({
  metricMap,
  pending
}: {
  metricMap: RedisMetricMap;
  pending: ReadonlySet<string>;
}) {
  const text = useRedisText();
  const linkValue = redisLatest(metricMap, 'redis_master_link_status');
  const link = linkTone(linkValue);
  const linkLoading = pending.has('redis_master_link_status') && linkValue == null;
  const active = redisLatest(metricMap, 'redis_repl_backlog_active');
  const enabled = flagOn(active);
  const stateLoading = pending.has('redis_repl_backlog_active') && active == null;
  const memory = redisDisplay(metricMap, 'redis_mem_replication_backlog', 'bytes');
  const memoryLoading = pending.has('redis_mem_replication_backlog') && memory.value == null;
  const memoryText = memory.value == null
    ? ''
    : (memory.unit ? `${memory.text}${memory.unit}` : memory.text);
  const stateLines = [
    text('backlogStateOpen'),
    text('backlogStateClosed')
  ];
  const memoryLines = [text('backlogMemoryLine')];
  const noSample = [text('backlogMemoryNoZero')];
  const lag = replicationOffsetLag(metricMap);
  const slavePoints = redisPoints(metricMap, 'redis_slave_repl_offset');
  const masterPoints = redisPoints(metricMap, 'redis_master_repl_offset');
  const slaves = redisLatest(metricMap, 'redis_connected_slaves');
  const waiting = lag == null && (
    (pending.has('redis_slave_repl_offset') && slavePoints.length === 0)
    || (pending.has('redis_master_repl_offset') && masterPoints.length === 0 && slavePoints.length > 0)
  );
  const noReplica = lag == null
    && slavePoints.length === 0
    && !(slaves != null && slaves > 0)
    && linkValue == null;
  const quietCopy = slavePoints.length === 0
    ? text('offsetSlaveEmpty')
    : masterPoints.length === 0
      ? text('offsetMasterEmpty')
      : text('offsetLagUnpaired');
  const lagTone = lag == null
    ? undefined
    : lag > 0
      ? 'var(--color-warning)'
      : lag < 0
        ? 'var(--color-text-2)'
        : 'var(--color-success)';

  return (
    <ReplicaStatusGrid>
      <StatusTile
        feature="link-status"
        label={text('cardLinkStatus')}
        hintKind="redis-link"
        lines={[text('linkLineHealthy'), text('linkLineDown'), text('linkLineQuiet')]}
        loading={linkLoading}
        value={link === 'up' ? text('linkHealthy') : link === 'down' ? text('linkDown') : undefined}
        tone={link === 'up' ? 'var(--color-success)' : link === 'down' ? 'var(--color-fail)' : undefined}
        empty={link === 'quiet' && !linkLoading ? text('linkEmpty') : undefined}
        accent={link === 'up' ? 'var(--color-success)' : link === 'down' ? 'var(--color-fail)' : undefined}
        dataAttrs={{
          'data-redis-link': link,
          'data-redis-link-scale': link === 'quiet' ? undefined : link
        }}
      />
      <StatusTile
        feature="backlog"
        label={text('backlogState')}
        hintKind="redis-backlog-state"
        lines={stateLines}
        locked={noSample}
        loading={stateLoading}
        value={enabled == null ? undefined : enabled ? text('backlogOn') : text('backlogOff')}
        empty={!stateLoading && enabled == null ? text('legendQuiet') : undefined}
        tone={enabled ? 'var(--color-success)' : 'var(--color-text-3)'}
        dataAttrs={{
          'data-redis-backlog': enabled == null ? 'quiet' : enabled ? 'on' : 'off',
          'data-redis-state': stateLoading ? 'loading' : 'ready',
          'data-redis-backlog-card': 'state'
        }}
      />
      <StatusTile
        feature="backlog-memory"
        label={text('backlogMemory')}
        hintKind="redis-backlog-memory"
        lines={memoryLines}
        locked={noSample}
        loading={memoryLoading}
        value={memoryText}
        empty={!memoryLoading && memory.value == null ? text('backlogMemoryEmpty') : undefined}
        dataAttrs={{
          'data-redis-backlog-memory': memory.value == null ? 'empty' : 'value'
        }}
      />
      <StatusTile
        feature="offset-lag"
        label={text('offsetLag')}
        hintKind="redis-offset-lag"
        lines={[
          text('offsetLagFormula'),
          text('offsetLagMissing'),
          text('offsetLagAligned'),
          text('offsetLagNegative')
        ]}
        loading={waiting}
        value={lag == null ? undefined : countText(lag)}
        tone={lagTone}
        empty={!waiting && lag == null ? (noReplica ? text('offsetNoReplica') : quietCopy) : undefined}
        dataAttrs={{
          'data-redis-offset-lag': waiting ? 'loading' : lag == null ? (noReplica ? 'no-replica' : 'quiet') : 'value'
        }}
      />
    </ReplicaStatusGrid>
  );
}

export function ReplicationPane({
  metricMap,
  pending,
  mode
}: {
  metricMap: RedisMetricMap;
  pending: ReadonlySet<string>;
  mode: ReplicationTabMode;
}) {
  const text = useRedisText();
  const showBacklog = BACKLOG_NAMES.some((name) => (
    redisLatest(metricMap, name) != null || pending.has(name)
  ));
  const offsetSeries = OFFSET_SERIES.filter((item) => redisLatest(metricMap, item.name) != null);
  const offsetPending = OFFSET_SERIES.some((item) => (
    pending.has(item.name) && redisLatest(metricMap, item.name) == null
  ));
  const offsetTrend: RedisTrendSpec = {
    titleKey: 'chartOffset',
    unit: 'counts',
    series: offsetSeries.map((item) => ({
      name: item.name,
      labelKey: item.labelKey,
      color: item.color
    }))
  };

  if (mode === 'gray') {
    return (
      <Pane pane="replication">
        <GrayTabEmptyState
          title={text('collectionNotReady')}
          hint={text('collectionNotReadyHint')}
        />
      </Pane>
    );
  }

  if (mode === 'loading') {
    return (
      <Pane pane="replication">
        <ProSection title={text('sectionReplicaStatus')}>
          <ReplicaStatusGrid>
            {(['link-status', 'backlog', 'backlog-memory', 'offset-lag'] as const).map((feature) => (
              <div
                key={feature}
                className={`${proChromeClass.kpiCard} ${proChromeClass.kpiCardLoading}`}
                data-redis-feature={feature}
                data-redis-state="loading"
              >
                <ProDashLoading size="small" layout="inline" />
              </div>
            ))}
          </ReplicaStatusGrid>
        </ProSection>
        <ProSection title={text('sectionLinks')}>
          <LoadingCard title={text('cardConnectedSlaves')} feature="connected-slaves" />
        </ProSection>
        <ProSection title={text('sectionBacklog')}>
          <LoadingCard title={text('backlogUsed')} feature="backlog-trends" />
        </ProSection>
        <ProSection title={text('sectionOffset')}>
          <LoadingCard title={text('chartOffset')} feature="offset" />
        </ProSection>
      </Pane>
    );
  }

  return (
    <Pane pane="replication">
      <ProSection title={text('sectionReplicaStatus')}>
        <ReplicaStatusRow metricMap={metricMap} pending={pending} />
      </ProSection>
      <ProSection title={text('sectionLinks')}>
        <ConnectedSlavesCard metricMap={metricMap} pending={pending} />
      </ProSection>
      {showBacklog ? (
        <ProSection title={text('sectionBacklog')}>
          <BacklogTrends metricMap={metricMap} pending={pending} />
        </ProSection>
      ) : null}
      {offsetSeries.length || offsetPending ? (
        <ProSection title={text('sectionOffset')}>
          {offsetSeries.length ? (
            <div className="min-w-0" data-redis-feature="offset">
              <RedisTrendChart spec={offsetTrend} metricMap={metricMap} pending={pending} />
            </div>
          ) : (
            <LoadingCard title={text('chartOffset')} feature="offset" />
          )}
        </ProSection>
      ) : null}
    </Pane>
  );
}

const CLUSTER_TREND: RedisTrendSpec = {
  titleKey: 'cardClusterConnections',
  emptyKey: 'clusterConnectionsEmpty',
  unit: 'counts',
  series: [{
    name: 'redis_cluster_connections',
    labelKey: 'cardClusterConnections',
    color: REDIS_PALETTE.blue
  }]
};

function ClusterConnectionsCard({
  metricMap,
  pending
}: {
  metricMap: RedisMetricMap;
  pending: ReadonlySet<string>;
}) {
  const text = useRedisText();
  const latest = redisLatest(metricMap, 'redis_cluster_connections');
  const loading = latest == null && pending.has('redis_cluster_connections');
  return (
    <div
      className="min-w-0"
      data-redis-feature="cluster-connections"
      data-redis-state={loading ? 'loading' : latest == null ? 'empty' : 'value'}
    >
      <RedisTrendChart
        spec={CLUSTER_TREND}
        metricMap={metricMap}
        pending={pending}
        hint={(
          <RedisHint
            kind="redis-cluster-connections"
            lines={[
              text('clusterConnectionsHint'),
              text('clusterConnectionsPeer'),
              text('clusterConnectionsEmptyHint')
            ]}
          />
        )}
      />
    </div>
  );
}

export function ClusterPane({
  metricMap,
  pending
}: {
  metricMap: RedisMetricMap;
  pending: ReadonlySet<string>;
}) {
  const text = useRedisText();
  return (
    <Pane pane="cluster">
      <ProSection title={text('sectionCluster')}>
        <ClusterConnectionsCard metricMap={metricMap} pending={pending} />
      </ProSection>
    </Pane>
  );
}
