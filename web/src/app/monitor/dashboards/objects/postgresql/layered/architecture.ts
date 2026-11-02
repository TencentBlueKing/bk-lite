export type PostgresFormLabel = '单机' | '主从';
export type PostgresRoleLabel = '主库' | '备库';

export interface PostgresIdentityReading {
  inRecovery: number | null;
  streamingReplicas: number | null;
  replicationSlots: number | null;
}

export interface PostgresIdentityView {
  form: PostgresFormLabel | null;
  role: PostgresRoleLabel | null;
}

const finite = (value: number | null | undefined): number | null => (
  value == null || !Number.isFinite(value) ? null : value
);

const near = (value: number, target: number) => Math.abs(value - target) < 1e-6;

/** 角色只认恢复状态：0 为主库（含单机），1 为备库。其它读数不猜。 */
export const postgresRoleLabel = (value: number | null | undefined): PostgresRoleLabel | null => {
  const reading = finite(value);
  if (reading == null) return null;
  if (near(reading, 0)) return '主库';
  if (near(reading, 1)) return '备库';
  return null;
};

const positiveCount = (value: number | null | undefined) => {
  const reading = finite(value);
  return reading != null && reading > 0;
};

const zeroCount = (value: number | null | undefined) => {
  const reading = finite(value);
  return reading != null && near(reading, 0);
};

/**
 * 顶栏形态与角色分开挂。
 * 备库、当前有流复制连接，或有复制槽 → 主从。
 * 主库且连接数、槽个数都采到 0 → 单机。
 * 主库但复制个数还没采到时不写成单机，避免把主从主库误标。
 * 没有集群采点，不写「集群」。判不出的那一枚不渲染。
 */
export const postgresIdentityView = (
  reading: PostgresIdentityReading
): PostgresIdentityView => {
  const role = postgresRoleLabel(reading.inRecovery);
  const hasReplica = positiveCount(reading.streamingReplicas) || positiveCount(reading.replicationSlots);
  let form: PostgresFormLabel | null = null;
  if (role === '备库' || hasReplica) {
    form = '主从';
  } else if (
    role === '主库'
    && zeroCount(reading.streamingReplicas)
    && zeroCount(reading.replicationSlots)
  ) {
    form = '单机';
  }
  return { form, role };
};
