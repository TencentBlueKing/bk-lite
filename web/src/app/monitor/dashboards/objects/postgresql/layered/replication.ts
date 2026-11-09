import type { ChartData } from '@/app/monitor/types';
import { formatMetricValue } from '../../../shared/utils/format';
import { postgresRoleLabel, type PostgresRoleLabel } from './architecture';
import { postgresLatest, postgresPoints, type PostgresMetricMap } from './series';

/** 写入 / 刷盘 / 回放延迟，以及复制槽仍留着的数据量。 */
export const POSTGRES_REPLICATION_LAG_METRIC_NAMES = [
  'postgresql_replication_write_lag_seconds',
  'postgresql_replication_flush_lag_seconds',
  'postgresql_replication_replay_lag_seconds',
  'postgresql_replication_slot_restart_lag_bytes'
] as const;

export type PostgresReplicationLagMetricName = (typeof POSTGRES_REPLICATION_LAG_METRIC_NAMES)[number];

/** 复制 Tab 要拉的指标：角色、连接、槽，再加上延迟与积压。 */
export const POSTGRES_REPLICATION_METRIC_NAMES = [
  'postgresql_recovery_in_recovery',
  'postgresql_replication_streaming_replicas',
  'postgresql_replication_replication_slots',
  ...POSTGRES_REPLICATION_LAG_METRIC_NAMES
] as const;

export type PostgresReplicationMetricName = (typeof POSTGRES_REPLICATION_METRIC_NAMES)[number];

export type PostgresReplicationLoad = 'loading' | 'ready' | 'not_collected';

export type PostgresReplicationNote = 'none' | 'unconfigured' | 'primary_no_downstream';

const RECOVERY: PostgresReplicationMetricName = 'postgresql_recovery_in_recovery';
const STREAMING: PostgresReplicationMetricName = 'postgresql_replication_streaming_replicas';
const SLOTS: PostgresReplicationMetricName = 'postgresql_replication_replication_slots';

const countText = (value: number | null) => (
  value == null ? '—' : Math.round(value).toLocaleString('zh-CN')
);

/** 有任一真实采样（含 0）即出数。全无序列才是未采集。查询未回时先保持加载，避免把 0 闪成未采集。 */
export const postgresReplicationLoad = (
  metricMap: PostgresMetricMap,
  pending: ReadonlySet<string>,
  booting = false
): PostgresReplicationLoad => {
  const anyPoint = POSTGRES_REPLICATION_METRIC_NAMES.some(
    (name) => postgresLatest(metricMap, name) != null
  );
  if (anyPoint) return 'ready';
  const waiting = booting || POSTGRES_REPLICATION_METRIC_NAMES.some((name) => pending.has(name));
  if (waiting) return 'loading';
  return 'not_collected';
};

export const postgresReplicationTabMode = (
  load: PostgresReplicationLoad
): 'ready' | 'loading' | 'empty' => {
  if (load === 'ready') return 'ready';
  if (load === 'loading') return 'loading';
  return 'empty';
};

/** 徽章「未采集」只在相关序列全部落定且没有样本时出现。 */
export const postgresReplicationDimmed = (load: PostgresReplicationLoad) => load === 'not_collected';

export interface PostgresReplicationModel {
  load: PostgresReplicationLoad;
  recovery: number | null;
  role: PostgresRoleLabel | null;
  roleText: string;
  rolePending: boolean;
  streaming: number | null;
  streamingText: string;
  streamingPending: boolean;
  slots: number | null;
  slotsText: string;
  slotsPending: boolean;
  note: PostgresReplicationNote;
  lag: PostgresReplicationLagModel;
}

const field = (
  metricMap: PostgresMetricMap,
  pending: ReadonlySet<string>,
  name: PostgresReplicationMetricName
) => {
  const value = postgresLatest(metricMap, name);
  return {
    value,
    pending: value == null && pending.has(name)
  };
};

/**
 * 有点且连接数、槽数都是采到的 0，才说明没有下游。
 * 备库自己通常没有下游连接，不把它说成「未配置复制」。
 * 缺任一项时不把缺失补成 0。
 */
export const postgresReplicationNote = ({
  role,
  streaming,
  slots,
  streamingPending,
  slotsPending
}: {
  role: PostgresRoleLabel | null;
  streaming: number | null;
  slots: number | null;
  streamingPending: boolean;
  slotsPending: boolean;
}): PostgresReplicationNote => {
  if (streamingPending || slotsPending) return 'none';
  if (streaming == null || slots == null) return 'none';
  if (streaming !== 0 || slots !== 0) return 'none';
  if (role === '备库') return 'none';
  if (role === '主库') return 'primary_no_downstream';
  return 'unconfigured';
};

export const readPostgresReplication = (
  metricMap: PostgresMetricMap,
  pending: ReadonlySet<string>,
  booting = false
): PostgresReplicationModel => {
  const recoveryField = field(metricMap, pending, RECOVERY);
  const streamingField = field(metricMap, pending, STREAMING);
  const slotsField = field(metricMap, pending, SLOTS);
  const role = postgresRoleLabel(recoveryField.value);
  return {
    load: postgresReplicationLoad(metricMap, pending, booting),
    recovery: recoveryField.value,
    role,
    roleText: recoveryField.pending ? '' : (role ?? '—'),
    rolePending: recoveryField.pending,
    streaming: streamingField.value,
    streamingText: streamingField.pending ? '' : countText(streamingField.value),
    streamingPending: streamingField.pending,
    slots: slotsField.value,
    slotsText: slotsField.pending ? '' : countText(slotsField.value),
    slotsPending: slotsField.pending,
    note: postgresReplicationNote({
      role,
      streaming: streamingField.value,
      slots: slotsField.value,
      streamingPending: streamingField.pending,
      slotsPending: slotsField.pending
    }),
    lag: readPostgresReplicationLag(metricMap, pending, booting)
  };
};

export type PostgresReplicationLagKey = 'write' | 'flush' | 'replay' | 'backlog';

export type PostgresReplicationLagState = 'loading' | 'ready' | 'absent';

export interface PostgresReplicationLagCard {
  key: PostgresReplicationLagKey;
  name: PostgresReplicationLagMetricName;
  unit: 's' | 'bytes';
  value: number | null;
  text: string;
  /** 真实采样。全 0 也保留，不另造非零点。 */
  points: ChartData[];
}

export interface PostgresReplicationLagModel {
  state: PostgresReplicationLagState;
  /** 有序列才是 lag。无点、未回都不画趋势。 */
  trends: 'lag' | 'none';
  cards: PostgresReplicationLagCard[];
}

const LAG_SPECS: ReadonlyArray<{
  key: PostgresReplicationLagKey;
  name: PostgresReplicationLagMetricName;
  unit: 's' | 'bytes';
}> = [
  { key: 'write', name: 'postgresql_replication_write_lag_seconds', unit: 's' },
  { key: 'flush', name: 'postgresql_replication_flush_lag_seconds', unit: 's' },
  { key: 'replay', name: 'postgresql_replication_replay_lag_seconds', unit: 's' },
  { key: 'backlog', name: 'postgresql_replication_slot_restart_lag_bytes', unit: 'bytes' }
];

/** 秒类可读。0 保留为 0s，不当成没采到。 */
export const formatPostgresLagSeconds = (value: number): string => {
  if (!Number.isFinite(value)) return '—';
  const formatted = formatMetricValue(value, 's');
  return `${formatted.value}${formatted.unit || ''}`;
};

/** 字节类人类可读。0 是 0 B，不换成缺失。 */
export const formatPostgresLagBytes = (value: number): string => {
  if (!Number.isFinite(value)) return '—';
  if (value === 0) return '0 B';
  const formatted = formatMetricValue(value, 'bytes');
  const unit = formatted.unit === 'Bytes' ? 'B' : formatted.unit;
  return unit ? `${formatted.value} ${unit}` : formatted.value;
};

const formatLagValue = (unit: 's' | 'bytes', value: number) => (
  unit === 'bytes' ? formatPostgresLagBytes(value) : formatPostgresLagSeconds(value)
);

/**
 * 四项里有任一点（含真实 0）就出数并允许画趋势。
 * 都没有样本时：查询还没回保持加载；全部落定才是本窗口未见采点。
 * 不把缺失补成 0，也不造非零点。
 */
export const readPostgresReplicationLag = (
  metricMap: PostgresMetricMap,
  pending: ReadonlySet<string>,
  booting = false
): PostgresReplicationLagModel => {
  const cards: PostgresReplicationLagCard[] = LAG_SPECS.map((spec) => {
    const value = postgresLatest(metricMap, spec.name);
    return {
      key: spec.key,
      name: spec.name,
      unit: spec.unit,
      value,
      text: value == null ? '—' : formatLagValue(spec.unit, value),
      points: postgresPoints(metricMap, spec.name)
    };
  });
  const anyPoint = cards.some((card) => card.value != null);
  if (anyPoint) {
    return {
      state: 'ready',
      trends: cards.some((card) => card.points.length > 0) ? 'lag' : 'none',
      cards
    };
  }
  const waiting = booting || POSTGRES_REPLICATION_LAG_METRIC_NAMES.some((name) => pending.has(name));
  return {
    state: waiting ? 'loading' : 'absent',
    trends: 'none',
    cards
  };
};
