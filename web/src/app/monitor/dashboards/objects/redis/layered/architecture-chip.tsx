'use client';

import { useDashboardText } from '../../../shared/utils/content-i18n';
import {
  inferArchitectureKind,
  replicationRoleLabel,
  type ArchitectureKind
} from './architecture-state';
import { redisCategoryText, type RedisCategoryCopyKey } from './redis-copy';
import { redisLatest, type RedisMetricMap } from './series';

const COPY: Record<ArchitectureKind, RedisCategoryCopyKey> = {
  cluster: 'archCluster',
  replica: 'archReplica',
  standalone: 'archStandalone',
  unknown: 'archUnknown'
};

function labeledRole(metricMap: RedisMetricMap): 'master' | 'slave' | null {
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
  return replicationRoleLabel(labels);
}

/** 实例名旁的架构芯片。推不出来时也保留「架构待识别」，不留空白。 */
export default function RedisArchitectureChip({ metricMap }: { metricMap: RedisMetricMap }) {
  const { t } = useDashboardText();
  const kind = inferArchitectureKind({
    clusterEnabled: redisLatest(metricMap, 'redis_cluster_enabled'),
    slaves: redisLatest(metricMap, 'redis_connected_slaves'),
    link: redisLatest(metricMap, 'redis_master_link_status'),
    labeledRole: labeledRole(metricMap)
  });
  const label = redisCategoryText(t, COPY[kind]);
  const known = kind !== 'unknown';
  return (
    <span
      data-redis-arch={kind}
      className={known
        ? 'inline-flex h-5 shrink-0 items-center rounded-full border border-[color-mix(in_srgb,var(--color-primary)_32%,var(--color-border))] bg-[color-mix(in_srgb,var(--color-primary)_10%,var(--color-bg))] px-2 text-[12px] font-medium leading-none text-[var(--color-text-1)]'
        : 'inline-flex h-5 shrink-0 items-center rounded-full border border-[var(--color-border)] bg-[var(--color-fill-2)] px-2 text-[12px] font-medium leading-none text-[var(--color-text-3)]'}
    >
      {label}
    </span>
  );
}
