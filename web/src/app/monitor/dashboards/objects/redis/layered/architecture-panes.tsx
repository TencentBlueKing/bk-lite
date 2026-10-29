'use client';

import { useMemo } from 'react';
import type { ReactNode } from 'react';
import { GrayTabEmptyState, ProDashLoading, ProInfoHint, ProSection } from '../../host/layered/pro-chrome';
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

/** 顶卡按内容收宽，不把两张 KPI 拉成各占半行的空盒。 */
const compactRow = styles.compactCards;

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
    <ProInfoHint
      kind={kind || 'redis-arch'}
      label={tipLines.join(' ')}
      text={tipLines.length === 1 ? tipLines[0] : undefined}
      content={tipLines.length > 1 ? (
        <div className="max-w-[380px] text-[13px] font-normal leading-[1.55] text-[var(--color-text-2)]">
          {tipLines.map((line) => (
            <p key={line} className="m-0 [&+&]:mt-2">{line}</p>
          ))}
        </div>
      ) : undefined}
    />
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
    <p className="m-0 text-[13px] font-medium leading-5 text-[var(--color-text-2)]" data-redis-empty="reading">
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

function formatReading(metricMap: RedisMetricMap, name: string, unit: MetricUnit) {
  const shown = redisDisplay(metricMap, name, unit);
  if (shown.value == null) return null;
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

const ROLE_VALUE: Record<RoleReading, RedisCategoryCopyKey> = {
  primary: 'rolePrimary',
  replica: 'roleReplica',
  'lean-primary': 'roleLeanPrimary',
  'lean-replica': 'roleLeanReplica',
  mixed: 'roleMixed'
};

function RoleCard({ role }: { role: RoleReading }) {
  const text = useRedisText();
  const labeled = role === 'primary' || role === 'replica';
  return (
    <section className={`${styles.panel} h-full`} data-redis-feature="role" data-redis-role={role}>
      <FeatureHead
        title={text('cardRole')}
        lines={[
          text('roleLinePrimary'),
          text('roleLineReplica'),
          text('roleLineLeanPrimary'),
          text('roleLineLeanReplica'),
          text('roleLineMixed'),
          text('roleLineSentinel')
        ]}
        kind="redis-role"
      />
      <div
        className={`text-[20px] font-semibold leading-7 ${labeled ? '!text-[var(--color-text-1)]' : '!text-[var(--color-text-2)]'}`}
      >
        {text(ROLE_VALUE[role])}
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
      <FeatureHead title={text('cardConnectedSlaves')} hint={text('connectedSlavesHint')} kind="redis-slaves" />
      {loading ? <ProDashLoading /> : shown.value == null ? (
        <QuietReading copy={text('slavesEmpty')} />
      ) : (
        <div className={`${styles.statValue} !text-[var(--color-text-1)]`}>
          {shown.text}
          {shown.unit ? <span className={styles.statUnit}>{shown.unit}</span> : null}
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
  const label = tone === 'up' ? text('linkHealthy') : text('linkDown');
  const valueClass = tone === 'up'
    ? '!text-[var(--color-success)]'
    : '!text-[var(--color-fail)]';
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
      <FeatureHead title={text('cardLinkStatus')} hint={text('linkHint')} kind="redis-link" />
      {loading ? <ProDashLoading /> : tone === 'quiet' ? (
        <div className="flex flex-col gap-1" data-redis-link-scale="hidden">
          <div className="text-[15px] font-semibold leading-6 text-[var(--color-text-1)]">{text('linkEmpty')}</div>
          <p className="m-0 text-[12px] leading-5 text-[var(--color-text-2)]">{text('linkEmptyTip')}</p>
        </div>
      ) : (
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
  const loading = BACKLOG_NAMES.every((name) => pending.has(name) || redisLatest(metricMap, name) == null)
    && BACKLOG_NAMES.some((name) => pending.has(name));
  const stateLabel = enabled ? text('backlogOn') : text('backlogOff');
  const stateClass = enabled ? 'text-[var(--color-success)]' : 'text-[var(--color-text-3)]';
  const usedText = formatReading(metricMap, 'redis_repl_backlog_histlen', 'bytes');
  const sizeText = formatReading(metricMap, 'redis_repl_backlog_size', 'bytes');
  const barFill = fill != null && enabled !== false ? fill : null;
  const ratio = usedText != null && sizeText != null
    ? `${usedText} / ${sizeText}${barFill != null ? ` · ${barFill.toFixed(1)}%` : ''}`
    : null;
  return (
    <section className={`${styles.panel} h-full`} data-redis-feature="backlog" data-redis-backlog={enabled == null ? 'quiet' : enabled ? 'on' : 'off'}>
      <FeatureHead
        title={text('cardBacklog')}
        lines={[
          text('backlogWritten'),
          text('backlogLimitExplain'),
          text('backlogPctExplain'),
          text('backlogHint')
        ]}
        kind="redis-backlog"
      />
      {loading ? <ProDashLoading /> : (
        <div className="flex flex-col gap-2">
          <p className="m-0 text-[13px] leading-5 text-[var(--color-text-1)]">
            <span className="text-[var(--color-text-3)]">{text('backlogState')}</span>
            {' '}
            {enabled == null ? text('backlogUnread') : (
              <span className={`font-semibold ${stateClass}`}>{stateLabel}</span>
            )}
          </p>
          {ratio != null ? (
            <p className="m-0 text-[15px] font-semibold leading-6 tabular-nums text-[var(--color-text-1)]" data-redis-backlog-ratio={ratio}>
              {ratio}
            </p>
          ) : enabled != null ? (
            <QuietReading copy={text('backlogUnread')} />
          ) : null}
          {barFill != null ? (
            <div
              className="h-2 overflow-hidden rounded-sm bg-[var(--color-fill-2)]"
              data-redis-backlog-fill={barFill.toFixed(1)}
            >
              <div
                className="h-full rounded-sm bg-[var(--color-text-2)]"
                style={{ width: `${barFill}%` }}
              />
            </div>
          ) : null}
        </div>
      )}
    </section>
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
          <div className={compactRow}>
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
        <div className={compactRow}>
          {role ? <RoleCard role={role} /> : null}
          <ConnectedSlavesCard metricMap={metricMap} pending={pending} />
          <LinkStatusCard metricMap={metricMap} pending={pending} />
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
            <RedisTrendChart spec={offsetTrend} metricMap={metricMap} pending={pending} />
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
      <FeatureHead title={text('cardClusterMode')} hint={text('clusterModeHint')} kind="redis-cluster-mode" />
      {phase === 'loading' ? <ProDashLoading /> : (
        <div className={`${styles.statValue} ${phase === 'on' ? '!text-[var(--color-success)]' : '!text-[var(--color-text-3)]'}`}>
          {phase === 'on' ? text('clusterOn') : text('clusterOff')}
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
      <FeatureHead title={text('cardClusterConnections')} hint={text('clusterConnectionsHint')} kind="redis-cluster-connections" />
      {loading ? <ProDashLoading /> : shown.value == null ? (
        <QuietReading copy={text('clusterConnectionsEmpty')} />
      ) : (
        <div className={`${styles.statValue} !text-[var(--color-text-1)]`}>
          {shown.text}
          {shown.unit ? <span className={styles.statUnit}>{shown.unit}</span> : null}
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
        <div className={compactRow}>
          <ClusterModeCard phase={phase} />
          <ClusterConnectionsCard metricMap={metricMap} pending={pending} />
        </div>
      </ProSection>
    </Pane>
  );
}
