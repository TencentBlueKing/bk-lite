'use client';

import { formatMssqlUptime, mssqlFormFromName, mssqlIdentityText } from './series';

const chipClass = (
  'inline-flex h-5 shrink-0 items-center rounded-full border border-[color-mix(in_srgb,var(--color-primary)_32%,var(--color-border))] bg-[color-mix(in_srgb,var(--color-primary)_10%,var(--color-bg))] px-2 text-[12px] font-medium leading-none text-[var(--color-text-1)]'
);

const FORM_CODE = {
  集群: 'cluster',
  单机: 'standalone'
} as const;

/**
 * 实例名旁的形态与次要事实。
 * 形态只在名字里有明确词时出现。没有主备事实，不挂角色，也不留空胶囊。
 */
export function MssqlIdentityExtra({
  instanceName,
  instanceId,
  idValues,
  uptimeMinutes,
  version,
  port
}: {
  instanceName: string;
  instanceId: string;
  idValues: readonly string[];
  uptimeMinutes: number | null;
  version: string;
  port: string;
}) {
  const form = mssqlFormFromName(mssqlIdentityText(instanceName, instanceId, ...idValues));
  const uptime = formatMssqlUptime(uptimeMinutes);
  const facts = [
    version,
    port ? `端口 ${port}` : '',
    uptime ? `运行 ${uptime}` : ''
  ].filter(Boolean);
  if (!form && facts.length === 0) return null;
  return (
    <span className="inline-flex min-w-0 max-w-full flex-wrap items-center gap-2" data-mssql-identity="">
      {form ? (
        <span className={chipClass} data-mssql-form={FORM_CODE[form]}>{form}</span>
      ) : null}
      {facts.length > 0 ? (
        <span className="min-w-0 text-[12px] leading-5 text-[var(--color-text-3)]" data-mssql-facts="">
          {facts.join(' · ')}
        </span>
      ) : null}
    </span>
  );
}
