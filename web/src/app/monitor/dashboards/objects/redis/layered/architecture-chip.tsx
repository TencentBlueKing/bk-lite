'use client';

import { useDashboardText } from '../../../shared/utils/content-i18n';
import { redisArchitectureView } from './architecture-view';
import type { ArchitectureKind, RoleReading } from './architecture-state';
import { redisCategoryText, type RedisCategoryCopyKey } from './redis-copy';
import type { RedisMetricMap } from './series';

const COPY: Record<Exclude<ArchitectureKind, 'unknown'>, RedisCategoryCopyKey> = {
  cluster: 'archCluster',
  replica: 'archReplica',
  standalone: 'archStandalone'
};

const ROLE_COPY: Record<RoleReading, RedisCategoryCopyKey> = {
  primary: 'rolePrimary',
  replica: 'roleReplica',
  'lean-primary': 'rolePrimary',
  'lean-replica': 'roleReplica',
  mixed: 'roleMixed'
};

const chipClass = (
  'inline-flex h-5 shrink-0 items-center rounded-full border border-[color-mix(in_srgb,var(--color-primary)_32%,var(--color-border))] bg-[color-mix(in_srgb,var(--color-primary)_10%,var(--color-bg))] px-2 text-[12px] font-medium leading-none text-[var(--color-text-1)]'
);

/** 实例名旁的架构芯片。集群开关未落地前不写「架构待识别」，也不抢先写成哨兵。 */
export default function RedisArchitectureChip({
  metricMap,
  instanceKey,
  pendingMetricNames,
  booting
}: {
  metricMap: RedisMetricMap;
  instanceKey: string;
  pendingMetricNames: ReadonlySet<string>;
  booting: boolean;
}) {
  const { t } = useDashboardText();
  const view = redisArchitectureView({
    instanceKey,
    metricMap,
    pending: pendingMetricNames,
    booting
  });
  if (view.kind === 'unknown') return null;
  const label = redisCategoryText(t, COPY[view.kind]);
  return (
    <span className="inline-flex h-5 max-w-full items-center gap-1" data-redis-arch={view.kind}>
      <span className={chipClass}>{label}</span>
      {view.role ? (
        <span className={chipClass} data-redis-arch-role={view.role}>
          {redisCategoryText(t, ROLE_COPY[view.role])}
        </span>
      ) : null}
    </span>
  );
}
