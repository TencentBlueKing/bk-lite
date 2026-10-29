'use client';

import { useDashboardText } from '../../../shared/utils/content-i18n';
import {
  inferArchitectureKind,
  inferReplicationRole,
  replicationRoleLabel,
  type ArchitectureKind,
  type RoleReading
} from './architecture-state';
import { redisCategoryText, type RedisCategoryCopyKey } from './redis-copy';
import { redisLatest, type RedisMetricMap } from './series';

const COPY: Record<ArchitectureKind, RedisCategoryCopyKey> = {
  cluster: 'archCluster',
  replica: 'archReplica',
  standalone: 'archStandalone',
  unknown: 'archUnknown'
};

const ROLE_COPY: Record<RoleReading, RedisCategoryCopyKey> = {
  primary: 'rolePrimary',
  replica: 'roleReplica',
  'lean-primary': 'roleLeanPrimary',
  'lean-replica': 'roleLeanReplica',
  mixed: 'roleMixed'
};

const chipClass = (known: boolean) => (
  known
    ? 'inline-flex h-5 shrink-0 items-center rounded-full border border-[color-mix(in_srgb,var(--color-primary)_32%,var(--color-border))] bg-[color-mix(in_srgb,var(--color-primary)_10%,var(--color-bg))] px-2 text-[12px] font-medium leading-none text-[var(--color-text-1)]'
    : 'inline-flex h-5 shrink-0 items-center rounded-full border border-[var(--color-border)] bg-[var(--color-fill-2)] px-2 text-[12px] font-medium leading-none text-[var(--color-text-3)]'
);

function roleLabels(metricMap: RedisMetricMap) {
  const labels: Array<Record<string, string> | undefined> = [];
  Object.values(metricMap).forEach((series) => {
    if (!series || series.loadState !== 'success') return;
    const points = series.viewData || [];
    for (let index = points.length - 1; index >= 0; index -= 1) {
      const metrics = points[index]?.seriesMetrics;
      if (!metrics) continue;
      const found = Object.values(metrics).filter((item) => item?.replication_role);
      if (!found.length) continue;
      labels.push(...found);
      break;
    }
  });
  return labels;
}

/** 实例名旁的架构芯片。推不出来时也保留「架构待识别」，不留空白。 */
export default function RedisArchitectureChip({ metricMap }: { metricMap: RedisMetricMap }) {
  const { t } = useDashboardText();
  const labels = roleLabels(metricMap);
  const slaves = redisLatest(metricMap, 'redis_connected_slaves');
  const link = redisLatest(metricMap, 'redis_master_link_status');
  const kind = inferArchitectureKind({
    clusterEnabled: redisLatest(metricMap, 'redis_cluster_enabled'),
    slaves,
    link,
    labeledRole: replicationRoleLabel(labels)
  });
  const role = kind === 'cluster'
    ? inferReplicationRole({ labels, slaves, link })
    : null;
  const label = redisCategoryText(t, COPY[kind]);
  const known = kind !== 'unknown';
  const chip = chipClass(known);
  if (kind !== 'cluster' || role == null) {
    return (
      <span data-redis-arch={kind} className={chip}>
        {label}
      </span>
    );
  }
  return (
    <span className="inline-flex h-5 max-w-full items-center gap-1" data-redis-arch={kind}>
      <span className={chip}>{label}</span>
      <span className={chip} data-redis-arch-role={role}>
        {redisCategoryText(t, ROLE_COPY[role])}
      </span>
    </span>
  );
}
