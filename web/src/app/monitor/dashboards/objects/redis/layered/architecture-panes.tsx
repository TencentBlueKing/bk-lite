'use client';

import { useMemo } from 'react';
import type { ReactNode } from 'react';
import { GrayTabEmptyState, ProDashLoading, ProSection } from '../../host/layered/pro-chrome';
import chart from '../../host/layered/layered.module.scss';
import { useDashboardText } from '../../../shared/utils/content-i18n';
import type { MetricUnit } from '../../../shared/types';
import { REDIS_PALETTE } from '../config';
import styles from '../index.module.scss';
import {
  backlogFill,
  clusterEnabledOn,
  flagOn,
  inferReplicationRole,
  linkTone,
  type ReplicationTabMode,
  type RoleReading
} from './architecture-state';
import { redisCategoryText, type RedisCategoryCopyKey } from './redis-copy';
import { redisDisplay, redisLatest, type RedisMetricMap } from './series';
import RedisTrendChart, { type RedisTrendSpec } from './trend-chart';

const featureGrid = 'grid min-w-0 grid-cols-1 items-stretch gap-3 lg:grid-cols-2';
const hintClass = 'm-0 text-[12px] leading-5 text-[var(--color-text-3)]';
const heroValueClass = 'flex items-baseline gap-2 text-[32px] font-bold leading-none tracking-tight tabular-nums sm:text-[40px]';

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

function useRedisText() {
  const { t } = useDashboardText();
  return (key: RedisCategoryCopyKey) => redisCategoryText(t, key);
}

function FeatureHead({ title }: { title: string }) {
  return (
    <div className={chart.chartHead}>
      <div className={chart.chartTitleGroup}>
        <div className={chart.chartTitleBlock}>
          <div className={chart.chartTitle}>{title}</div>
        </div>
      </div>
    </div>
  );
}

function Pane({ pane, children }: { pane: string; children: ReactNode }) {
  return (
    <div data-redis-pane={pane} className="contents">
      {children}
    </div>
  );
}

function formatReading(metricMap: RedisMetricMap, name: string, unit: MetricUnit) {
  const shown = redisDisplay(metricMap, name, unit);
  return shown.unit ? `${shown.text} ${shown.unit}` : shown.text;
}

function roleLabels(metricMap: RedisMetricMap) {
  const labels: Array<Record<string, string> | undefined> = [];
  Object.values(metricMap).forEach((series) => {
    if (!series || series.loadState !== 'success') return;
    const points = series.viewData || [];
    for (let index = points.length - 1; index >= 0; index -= 1) {
      const found = Object.values(points[index].seriesMetrics || {}).filter((item) => item?.replication_role);
      if (!found.length) continue;
      labels.push(...found);
      break;
    }
  });
  return labels;
}

function LoadingCard({ title, feature }: { title: string; feature: string }) {
  return (
    <section className={`${styles.panel} h-full`} data-redis-feature={feature} data-redis-state="loading">
      <FeatureHead title={title} />
      <ProDashLoading />
    </section>
  );
}

const ROLE_COPY: Record<RoleReading, { value: RedisCategoryCopyKey; hint: RedisCategoryCopyKey }> = {
  primary: { value: 'rolePrimary', hint: 'rolePrimaryHint' },
  replica: { value: 'roleReplica', hint: 'roleReplicaHint' },
  'lean-primary': { value: 'roleLeanPrimary', hint: 'roleLeanPrimaryHint' },
  'lean-replica': { value: 'roleLeanReplica', hint: 'roleLeanReplicaHint' },
  mixed: { value: 'roleMixed', hint: 'roleMixedHint' }
};

function RoleCard({ role }: { role: RoleReading }) {
  const text = useRedisText();
  const labeled = role === 'primary' || role === 'replica';
  const copy = ROLE_COPY[role];
  const value = text(copy.value);
  const hint = text(copy.hint);
  return (
    <section className={`${styles.panel} h-full`} data-redis-feature="role" data-redis-role={role}>
      <FeatureHead title={text('cardRole')} />
      <div className="flex flex-col gap-2">
        <div
          className={`text-[20px] font-semibold leading-none ${labeled ? '!text-[var(--color-text-1)]' : '!text-[var(--color-text-2)]'}`}
        >
          {value}
        </div>
        <p className={hintClass}>{hint}</p>
      </div>
    </section>
  );
}

function ConnectedSlavesCard({
  metricMap,
  pending
}: {
  metricMap: RedisMetricMap;
  pending: ReadonlySet<string>;
}) {
  const text = useRedisText();
  const shown = redisDisplay(metricMap, 'redis_connected_slaves', 'counts');
  const loading = pending.has('redis_connected_slaves') && shown.value == null;
  return (
    <section
      className={`${styles.panel} h-full`}
      data-redis-feature="connected-slaves"
      data-redis-emphasis="hero"
    >
      <FeatureHead title={text('cardConnectedSlaves')} />
      {loading ? <ProDashLoading /> : (
        <div className="flex flex-col gap-2">
          <div
            className={`${heroValueClass} ${shown.value == null ? '!text-[var(--color-text-3)]' : '!text-[var(--color-text-1)]'}`}
          >
            {shown.text}
            {shown.unit ? <span className={styles.statUnit}>{shown.unit}</span> : null}
          </div>
          <p className={hintClass}>{text('connectedSlavesHint')}</p>
        </div>
      )}
    </section>
  );
}

function LinkStatusCard({
  metricMap,
  pending
}: {
  metricMap: RedisMetricMap;
  pending: ReadonlySet<string>;
}) {
  const text = useRedisText();
  const value = redisLatest(metricMap, 'redis_master_link_status');
  const tone = linkTone(value);
  const loading = pending.has('redis_master_link_status') && value == null;
  const label = tone === 'up' ? text('linkHealthy') : tone === 'down' ? text('linkDown') : '--';
  const valueClass = tone === 'up'
    ? '!text-[var(--color-success)]'
    : tone === 'down'
      ? '!text-[var(--color-fail)]'
      : '!text-[var(--color-text-3)]';
  const bands = [
    {
      key: 'up' as const,
      label: text('linkHealthy'),
      onClass: 'bg-[color-mix(in_srgb,var(--color-success)_14%,var(--color-bg))] font-semibold text-[var(--color-success)]'
    },
    {
      key: 'down' as const,
      label: text('linkDown'),
      onClass: 'bg-[color-mix(in_srgb,var(--color-fail)_14%,var(--color-bg))] font-semibold text-[var(--color-fail)]'
    }
  ];
  return (
    <section
      className={`${styles.panel} h-full`}
      data-redis-feature="link-status"
      data-redis-link={tone}
    >
      <FeatureHead title={text('cardLinkStatus')} />
      {loading ? <ProDashLoading /> : (
        <div className="flex flex-col gap-3">
          <div className={`${styles.statValue} ${valueClass}`}>{label}</div>
          <div className="flex gap-1.5" data-redis-link-scale={tone}>
            {bands.map((band) => {
              const on = band.key === tone;
              return (
                <span
                  key={band.key}
                  className={`inline-flex h-6 flex-1 items-center justify-center rounded-md text-[12px] ${on ? band.onClass : 'bg-[var(--color-fill-2)] font-normal text-[var(--color-text-3)]'}`}
                >
                  {band.label}
                </span>
              );
            })}
          </div>
          <p className={hintClass}>{text('linkHint')}</p>
        </div>
      )}
    </section>
  );
}

function BacklogCard({
  metricMap,
  pending
}: {
  metricMap: RedisMetricMap;
  pending: ReadonlySet<string>;
}) {
  const text = useRedisText();
  const active = redisLatest(metricMap, 'redis_repl_backlog_active');
  const enabled = flagOn(active);
  const fill = backlogFill(
    redisLatest(metricMap, 'redis_repl_backlog_histlen'),
    redisLatest(metricMap, 'redis_repl_backlog_size')
  );
  const memory = redisLatest(metricMap, 'redis_mem_replication_backlog');
  const loading = BACKLOG_NAMES.every((name) => pending.has(name) || redisLatest(metricMap, name) == null)
    && BACKLOG_NAMES.some((name) => pending.has(name));
  const stateLabel = enabled == null ? '--' : enabled ? text('backlogOn') : text('backlogOff');
  const stateClass = enabled ? 'text-[var(--color-success)]' : 'text-[var(--color-text-3)]';
  return (
    <section className={`${styles.panel} h-full`} data-redis-feature="backlog" data-redis-backlog={enabled == null ? 'quiet' : enabled ? 'on' : 'off'}>
      <FeatureHead title={text('cardBacklog')} />
      {loading ? <ProDashLoading /> : (
        <div className="flex flex-col gap-3">
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-[12px] text-[var(--color-text-3)]">{text('backlogState')}</span>
            <span className={`text-[14px] font-semibold ${stateClass}`}>{stateLabel}</span>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <div className="text-[12px] text-[var(--color-text-3)]">{text('backlogUsed')}</div>
              <div className={styles.statValue}>{formatReading(metricMap, 'redis_repl_backlog_histlen', 'bytes')}</div>
            </div>
            <div>
              <div className="text-[12px] text-[var(--color-text-3)]">{text('backlogCapacity')}</div>
              <div className={styles.statValue}>{formatReading(metricMap, 'redis_repl_backlog_size', 'bytes')}</div>
            </div>
          </div>
          {fill != null ? (
            <div className="h-2 overflow-hidden rounded-sm bg-[var(--color-fill-2)]" data-redis-backlog-fill={fill.toFixed(1)}>
              <div
                className={`h-full rounded-sm ${enabled === false ? 'bg-[var(--color-text-4)]' : 'bg-[var(--color-text-2)]'}`}
                style={{ width: `${fill}%` }}
              />
            </div>
          ) : null}
          {memory != null ? (
            <p className="m-0 text-[13px] tabular-nums text-[var(--color-text-1)]">
              {text('backlogMemory')}
              {' '}
              {formatReading(metricMap, 'redis_mem_replication_backlog', 'bytes')}
            </p>
          ) : null}
          <p className={hintClass}>{text('backlogHint')}</p>
        </div>
      )}
    </section>
  );
}

function OffsetReadings({ metricMap }: { metricMap: RedisMetricMap }) {
  const text = useRedisText();
  const cells = [
    { feature: 'master-offset', label: text('cardMasterOffset'), name: 'redis_master_repl_offset' },
    { feature: 'slave-offset', label: text('cardSlaveOffset'), name: 'redis_slave_repl_offset' }
  ];
  return (
    <div className={featureGrid}>
      {cells.map((cell) => (
        <section key={cell.name} className={`${styles.panel} h-full`} data-redis-feature={cell.feature}>
          <FeatureHead title={cell.label} />
          <div className={styles.statValue}>{formatReading(metricMap, cell.name, 'counts')}</div>
        </section>
      ))}
    </div>
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
  const role = useMemo(() => inferReplicationRole({
    labels: roleLabels(metricMap),
    slaves: redisLatest(metricMap, 'redis_connected_slaves'),
    link: redisLatest(metricMap, 'redis_master_link_status')
  }), [metricMap]);
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
        <ProSection title={text('sectionLinks')}>
          <div className={featureGrid}>
            <LoadingCard title={text('cardConnectedSlaves')} feature="connected-slaves" />
            <LoadingCard title={text('cardLinkStatus')} feature="link-status" />
          </div>
        </ProSection>
        <ProSection title={text('sectionBacklog')}>
          <LoadingCard title={text('cardBacklog')} feature="backlog" />
        </ProSection>
        <ProSection title={text('sectionOffset')}>
          <LoadingCard title={text('chartOffset')} feature="offset" />
        </ProSection>
      </Pane>
    );
  }

  return (
    <Pane pane="replication">
      <ProSection title={text('sectionLinks')}>
        <div className="flex min-w-0 flex-col gap-3">
          {role ? <RoleCard role={role} /> : null}
          <div className={featureGrid}>
            <ConnectedSlavesCard metricMap={metricMap} pending={pending} />
            <LinkStatusCard metricMap={metricMap} pending={pending} />
          </div>
        </div>
      </ProSection>
      {showBacklog ? (
        <ProSection title={text('sectionBacklog')}>
          <BacklogCard metricMap={metricMap} pending={pending} />
        </ProSection>
      ) : null}
      {offsetSeries.length || offsetPending ? (
        <ProSection title={text('sectionOffset')}>
          {offsetSeries.length ? (
            <div className="flex min-w-0 flex-col gap-3">
              <OffsetReadings metricMap={metricMap} />
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

function ClusterModeCard({ phase }: { phase: 'on' | 'off' | 'loading' }) {
  const text = useRedisText();
  return (
    <section
      className={`${styles.panel} h-full`}
      data-redis-feature="cluster-mode"
      data-redis-cluster={phase}
      data-redis-emphasis="hero"
    >
      <FeatureHead title={text('cardClusterMode')} />
      {phase === 'loading' ? <ProDashLoading /> : (
        <div className="flex flex-col gap-2">
          <div
            className={`${heroValueClass} ${phase === 'on' ? 'text-[var(--color-success)]' : 'text-[var(--color-text-3)]'}`}
          >
            {phase === 'on' ? text('clusterOn') : text('clusterOff')}
          </div>
          <p className={hintClass}>{text('clusterModeHint')}</p>
        </div>
      )}
    </section>
  );
}

function ClusterConnectionsCard({
  metricMap,
  pending
}: {
  metricMap: RedisMetricMap;
  pending: ReadonlySet<string>;
}) {
  const text = useRedisText();
  const shown = redisDisplay(metricMap, 'redis_cluster_connections', 'counts');
  const loading = pending.has('redis_cluster_connections') && shown.value == null;
  return (
    <section className={`${styles.panel} h-full`} data-redis-feature="cluster-connections">
      <FeatureHead title={text('cardClusterConnections')} />
      {loading ? <ProDashLoading /> : (
        <div className="flex flex-col gap-2">
          <div
            className={`${styles.statValue} ${shown.value == null ? '!text-[var(--color-text-3)]' : '!text-[var(--color-text-1)]'}`}
          >
            {shown.text}
            {shown.unit ? <span className={styles.statUnit}>{shown.unit}</span> : null}
          </div>
          <p className={hintClass}>{text('clusterConnectionsHint')}</p>
        </div>
      )}
    </section>
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
  const enabledValue = redisLatest(metricMap, 'redis_cluster_enabled');
  const phase = pending.has('redis_cluster_enabled') && enabledValue == null
    ? 'loading'
    : clusterEnabledOn(enabledValue)
      ? 'on'
      : 'off';
  return (
    <Pane pane="cluster">
      <ProSection title={text('sectionCluster')}>
        <div className={featureGrid}>
          <ClusterModeCard phase={phase} />
          <ClusterConnectionsCard metricMap={metricMap} pending={pending} />
        </div>
      </ProSection>
    </Pane>
  );
}
