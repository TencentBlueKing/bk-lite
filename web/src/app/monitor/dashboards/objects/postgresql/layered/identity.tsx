'use client';

import { useEffect, useState, type Key } from 'react';
import useViewApi from '@/app/monitor/api/view';
import type { TimeValuesProps } from '@/app/monitor/types';
import { buildSearchParams, toMetricSeries } from '../../../shared/utils';
import { latestNumber } from '../../host/layered/readings';
import { POSTGRES_RECOVERY_QUERY } from '../queries';
import {
  postgresFormFromName,
  postgresIdentityText,
  postgresRoleLabel,
  visiblePostgresForm,
  type PostgresFormLabel
} from './architecture';

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

const FORM_CODE: Record<PostgresFormLabel, string> = {
  集群: 'cluster',
  主从: 'replica',
  单机: 'standalone'
};

/**
 * 形态优先看对象名/标识，其次看是否真有 recovery 序列。
 * 角色只认该序列的 0/1。没有依据就不渲染，不用名字猜主备，也不写「实例」或「—」。
 */
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

  const nameForm = postgresFormFromName(
    postgresIdentityText(instanceName, String(instanceId ?? ''), ...idValues)
  );
  const recoveryPresent = inRecovery != null && Number.isFinite(inRecovery);
  const form = visiblePostgresForm(nameForm, recoveryPresent, pending);
  const role = pending ? null : postgresRoleLabel(inRecovery);
  if (!form && !role) return null;
  return (
    <span className="inline-flex h-5 max-w-full items-center gap-1" data-postgres-identity="">
      {form ? (
        <span className={chipClass} data-postgres-form={FORM_CODE[form]}>{form}</span>
      ) : null}
      {role ? (
        <span className={chipClass} data-postgres-role={role === '主库' ? 'primary' : 'standby'}>
          {role}
        </span>
      ) : null}
    </span>
  );
}
