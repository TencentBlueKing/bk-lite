'use client';

import { useEffect, useState, type Key } from 'react';
import useViewApi from '@/app/monitor/api/view';
import type { TimeValuesProps } from '@/app/monitor/types';
import { buildSearchParams, toMetricSeries } from '../../../shared/utils';
import { latestNumber } from '../../host/layered/readings';
import { POSTGRES_RECOVERY_QUERY } from '../queries';

const chipClass = (
  'inline-flex h-5 shrink-0 items-center rounded-full border border-[color-mix(in_srgb,var(--color-primary)_32%,var(--color-border))] bg-[color-mix(in_srgb,var(--color-primary)_10%,var(--color-bg))] px-2 text-[12px] font-medium leading-none text-[var(--color-text-1)]'
);

const recoveryMetric = {
  name: 'postgresql_recovery_in_recovery',
  display_name: '是否处于恢复',
  description: '0 表示正在接受写入（含单机），1 表示仍在回放的备库。',
  unit: 'none' as const,
  query: POSTGRES_RECOVERY_QUERY,
  color: '#6366F1'
};

/**
 * 角色只认恢复状态采点：0 为主库（含单机），1 为备库。
 * 没有采点、查询失败或数值不是 0/1 时不渲染芯片。不用实例名猜主备，也不写「实例」。
 */
export const postgresRoleLabel = (value: number | null | undefined): '主库' | '备库' | null => {
  if (value == null || !Number.isFinite(value)) return null;
  if (Math.abs(value) < 1e-6) return '主库';
  if (Math.abs(value - 1) < 1e-6) return '备库';
  return null;
};

export function PostgresIdentityPills({
  instanceId,
  monitorObjectId,
  instanceName,
  idValues,
  instanceIdKeys,
  timeValues,
  minStepSeconds,
  reloadKey = 0
}: {
  instanceId: Key;
  monitorObjectId: Key;
  instanceName: string;
  idValues: string[];
  instanceIdKeys: string[];
  timeValues: TimeValuesProps;
  minStepSeconds?: number;
  reloadKey?: number;
}) {
  const { getInstanceQuery } = useViewApi();
  const [inRecovery, setInRecovery] = useState<number | null>(null);
  const [pending, setPending] = useState(true);
  const identity = `${idValues.join('\u0001')}::${instanceIdKeys.join('\u0001')}`;

  useEffect(() => {
    const [valueKey, keyKey = ''] = identity.split('::');
    const values = valueKey ? valueKey.split('\u0001') : [];
    const keys = keyKey ? keyKey.split('\u0001') : [];
    if (!values.length || !instanceId) {
      setInRecovery(null);
      setPending(false);
      return undefined;
    }
    let active = true;
    setPending(true);
    getInstanceQuery(buildSearchParams(
      recoveryMetric.query,
      recoveryMetric.unit,
      values,
      keys,
      timeValues,
      undefined,
      false,
      minStepSeconds,
      { monitorObjectId: String(monitorObjectId || ''), instanceId: String(instanceId) }
    )).then((result) => {
      if (!active) return;
      setInRecovery(latestNumber(toMetricSeries(
        recoveryMetric,
        result,
        instanceId,
        instanceName,
        values,
        keys
      )));
      setPending(false);
    }).catch(() => {
      if (!active) return;
      setInRecovery(null);
      setPending(false);
    });
    return () => {
      active = false;
    };
  }, [
    getInstanceQuery,
    identity,
    instanceId,
    instanceName,
    minStepSeconds,
    monitorObjectId,
    reloadKey,
    timeValues
  ]);

  if (pending) return null;
  const role = postgresRoleLabel(inRecovery);
  if (!role) return null;
  return (
    <span className="inline-flex h-5 max-w-full items-center gap-1" data-postgres-identity="">
      <span
        className={chipClass}
        data-postgres-role={role === '主库' ? 'primary' : 'standby'}
      >
        {role}
      </span>
    </span>
  );
}
