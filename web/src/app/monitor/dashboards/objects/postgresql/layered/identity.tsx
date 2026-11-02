'use client';

import { useEffect, useState, type Key } from 'react';
import useViewApi from '@/app/monitor/api/view';
import type { TimeValuesProps } from '@/app/monitor/types';
import { buildSearchParams, toMetricSeries } from '../../../shared/utils';
import { latestNumber } from '../../host/layered/readings';
import {
  POSTGRES_RECOVERY_QUERY,
  POSTGRES_REPLICATION_SLOTS_QUERY,
  POSTGRES_STREAMING_REPLICAS_QUERY
} from '../queries';
import { postgresIdentityView, type PostgresIdentityReading } from './architecture';

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

const streamingMetric = {
  name: 'postgresql_replication_streaming_replicas',
  display_name: '流复制连接数',
  description: '当前连着的流复制对端个数。0 是采点。',
  unit: 'counts' as const,
  query: POSTGRES_STREAMING_REPLICAS_QUERY,
  color: '#6366F1'
};

const slotsMetric = {
  name: 'postgresql_replication_replication_slots',
  display_name: '复制槽个数',
  description: '复制槽个数，包含暂时没连上的槽。0 是采点。',
  unit: 'counts' as const,
  query: POSTGRES_REPLICATION_SLOTS_QUERY,
  color: '#6366F1'
};

interface IdentityMetric {
  name: string;
  display_name: string;
  description: string;
  unit: 'none' | 'counts';
  query: string;
  color: string;
}

const FORM_CODE = { 单机: 'standalone', 主从: 'replica' } as const;
const ROLE_CODE = { 主库: 'primary', 备库: 'standby' } as const;

/**
 * 形态和角色各自有采点才挂。没有集群采点，不写「集群」。
 * 判不出时不渲染那一枚，也不写「实例」或「—」。
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
  const [reading, setReading] = useState<PostgresIdentityReading | null>(null);
  const identity = `${idValues.join('\u0001')}::${instanceIdKeys.join('\u0001')}`;

  useEffect(() => {
    const [valueKey, keyKey = ''] = identity.split('::');
    const values = valueKey ? valueKey.split('\u0001') : [];
    const keys = keyKey ? keyKey.split('\u0001') : [];
    if (!values.length || !instanceId) {
      setReading({ inRecovery: null, streamingReplicas: null, replicationSlots: null });
      return undefined;
    }
    let active = true;
    setReading(null);
    const context = { monitorObjectId: String(monitorObjectId || ''), instanceId: String(instanceId) };
    const load = (metric: IdentityMetric) => getInstanceQuery(buildSearchParams(
      metric.query,
      metric.unit,
      values,
      keys,
      timeValues,
      undefined,
      false,
      minStepSeconds,
      context
    )).then((result) => latestNumber(toMetricSeries(
      metric,
      result,
      instanceId,
      instanceName,
      values,
      keys
    ))).catch(() => null);
    Promise.all([load(recoveryMetric), load(streamingMetric), load(slotsMetric)]).then(([
      inRecovery,
      streamingReplicas,
      replicationSlots
    ]) => {
      if (!active) return;
      setReading({ inRecovery, streamingReplicas, replicationSlots });
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

  if (!reading) return null;
  const view = postgresIdentityView(reading);
  if (!view.form && !view.role) return null;
  return (
    <span className="inline-flex h-5 max-w-full items-center gap-1" data-postgres-identity="">
      {view.form ? (
        <span className={chipClass} data-postgres-form={FORM_CODE[view.form]}>
          {view.form}
        </span>
      ) : null}
      {view.role ? (
        <span className={chipClass} data-postgres-role={ROLE_CODE[view.role]}>
          {view.role}
        </span>
      ) : null}
    </span>
  );
}
