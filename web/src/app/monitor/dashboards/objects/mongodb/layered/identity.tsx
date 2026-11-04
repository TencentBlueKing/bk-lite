'use client';

import { formatDuration } from '../../common/simple-dashboard-core';
import type { LinkedHostCandidate } from '../../../shared/linked-host';
import { LinkedHostSegment } from '../../../shared/widgets/linked-host-segment';
import { mongoForm, mongoIdentityText, mongoRole, type MongoFormLabel } from './architecture';

const chipClass = (
  'inline-flex h-5 shrink-0 items-center rounded-full border border-[color-mix(in_srgb,var(--color-primary)_32%,var(--color-border))] bg-[color-mix(in_srgb,var(--color-primary)_10%,var(--color-bg))] px-2 text-[12px] font-medium leading-none text-[var(--color-text-1)]'
);

const FORM_CODE: Record<MongoFormLabel, string> = {
  单机: 'standalone',
  主从: 'replica'
};

const Sep = () => <span className="text-[var(--color-text-4)]" aria-hidden="true">·</span>;

/**
 * 专业盘实例名下的一行。形态和角色有依据才出现。
 * 所属主机槽始终在，没有关联时显示「无所属主机」。
 */
export function MongoIdentityLine({
  instanceName,
  instanceId,
  idValues,
  databaseRole,
  version,
  port,
  uptimeSeconds,
  host,
  hostHref,
  hostPending
}: {
  instanceName: string;
  instanceId: string;
  idValues: readonly string[];
  databaseRole: string;
  version: string;
  port: string;
  uptimeSeconds: number | null;
  host: LinkedHostCandidate | null;
  hostHref: string;
  hostPending: boolean;
}) {
  const nameText = mongoIdentityText(instanceName, instanceId, ...idValues);
  const form = mongoForm(nameText, databaseRole);
  const role = mongoRole(databaseRole);
  const facts = [
    version,
    port ? `端口 ${port}` : '',
    uptimeSeconds != null && Number.isFinite(uptimeSeconds) && uptimeSeconds >= 0
      ? `运行 ${formatDuration(uptimeSeconds)}`
      : ''
  ].filter(Boolean);

  return (
    <span
      className="inline-flex min-w-0 max-w-full flex-wrap items-center gap-x-2 gap-y-1 text-[12px] leading-5 text-[var(--color-text-3)]"
      data-mongodb-identity=""
    >
      {form ? (
        <span className={chipClass} data-mongodb-form={FORM_CODE[form]}>{form}</span>
      ) : null}
      {role ? (
        <span className={chipClass} data-mongodb-role={role === '主库' ? 'primary' : 'secondary'}>
          {role}
        </span>
      ) : null}
      {facts.map((fact) => (
        <span key={fact} className="inline-flex items-center gap-2">
          {form || role || facts[0] !== fact ? <Sep /> : null}
          <span>{fact}</span>
        </span>
      ))}
      {facts.length || form || role ? <Sep /> : null}
      <LinkedHostSegment host={host} href={hostHref} pending={hostPending} />
    </span>
  );
}
