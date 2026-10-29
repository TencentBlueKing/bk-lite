/** 主从链接。采集侧把 up/down 收成数值：1 健康，0 断链。其它读数不改写成拓扑。 */
export type LinkTone = 'up' | 'down' | 'quiet';

/**
 * 标签优先。没有标签时：只有副本连接偏主，只有主从链接偏从。
 * 两侧读数都在时不猜成单一角色，只说明主从读数都在。都没有则不出卡。
 */
export type RoleReading = 'primary' | 'replica' | 'lean-primary' | 'lean-replica' | 'mixed';

export type ReplicationTabMode = 'loading' | 'gray' | 'ready';

const finite = (value: number | null | undefined) => (
  value == null || !Number.isFinite(value) ? null : value
);

export const linkTone = (value: number | null | undefined): LinkTone => {
  const reading = finite(value);
  if (reading === 1) return 'up';
  if (reading === 0) return 'down';
  return 'quiet';
};

/** 1 开启 / 已启用，0 关闭 / 未启用。其它值不当成布尔。 */
export const flagOn = (value: number | null | undefined): boolean | null => {
  const reading = finite(value);
  if (reading === 1) return true;
  if (reading === 0) return false;
  return null;
};

/** 集群模式采样是否为开启。空值和 0 都不是开启。 */
export const clusterEnabledOn = (enabled: number | null | undefined) => finite(enabled) === 1;

/**
 * 记住本实例是否见过 cluster_enabled=1。
 * 时间窗重拉会先删掉序列再标 pending；这段空窗继续显 Cluster，避免跳回概览。
 * 换实例清掉记忆。查询落地后不是 1，再藏。
 */
export const nextClusterSeen = ({
  enabled,
  inflight,
  seen,
  instanceChanged
}: {
  enabled: number | null | undefined;
  inflight: boolean;
  seen: boolean;
  instanceChanged: boolean;
}) => {
  if (instanceChanged) return clusterEnabledOn(enabled);
  if (clusterEnabledOn(enabled)) return true;
  if (inflight) return seen;
  return false;
};

/** 当前是 1，或本实例刚见过 1 且这次采样还在飞，才显 Cluster。首屏未证实前不闪出。 */
export const clusterTabVisible = ({
  enabled,
  inflight,
  seen
}: {
  enabled: number | null | undefined;
  inflight: boolean;
  seen: boolean;
}) => clusterEnabledOn(enabled) || (inflight && seen);

export const backlogFill = (
  used: number | null | undefined,
  size: number | null | undefined
): number | null => {
  const usedValue = finite(used);
  const sizeValue = finite(size);
  if (usedValue == null || sizeValue == null || sizeValue <= 0) return null;
  return Math.min(100, Math.max(0, (usedValue / sizeValue) * 100));
};

export const replicationRoleLabel = (
  labels: readonly (Record<string, string> | undefined)[]
): 'master' | 'slave' | null => {
  let master = false;
  let slave = false;
  labels.forEach((item) => {
    const role = String(item?.replication_role || '').trim().toLowerCase();
    if (role === 'master') master = true;
    if (role === 'slave' || role === 'replica') slave = true;
  });
  if (master && !slave) return 'master';
  if (slave && !master) return 'slave';
  return null;
};

export const inferReplicationRole = ({
  labels,
  slaves,
  link
}: {
  labels: readonly (Record<string, string> | undefined)[];
  slaves: number | null | undefined;
  link: number | null | undefined;
}): RoleReading | null => {
  const labeled = replicationRoleLabel(labels);
  if (labeled === 'master') return 'primary';
  if (labeled === 'slave') return 'replica';
  const hasSlaves = (finite(slaves) ?? 0) > 0;
  const hasLink = finite(link) != null;
  if (hasSlaves && hasLink) return 'mixed';
  if (hasSlaves) return 'lean-primary';
  if (hasLink) return 'lean-replica';
  return null;
};

export type ArchitectureKind = 'cluster' | 'replica' | 'standalone' | 'unknown';

/**
 * 架构芯片。Cluster 优先；有副本连接、主从链接或角色标签则为哨兵/副本。
 * 只有集群明确关闭、副本数为 0、且没有主从链接时才判单机。其余保持待识别，避免把加载中写成单机。
 */
export const inferArchitectureKind = ({
  clusterEnabled,
  slaves,
  link,
  labeledRole
}: {
  clusterEnabled: number | null | undefined;
  slaves: number | null | undefined;
  link: number | null | undefined;
  labeledRole: 'master' | 'slave' | null;
}): ArchitectureKind => {
  if (clusterEnabledOn(clusterEnabled)) return 'cluster';
  const slaveCount = finite(slaves);
  const linkValue = finite(link);
  const hasReplica = (slaveCount ?? 0) > 0 || linkValue != null || labeledRole != null;
  if (hasReplica) return 'replica';
  if (finite(clusterEnabled) === 0 && slaveCount === 0 && linkValue == null && labeledRole == null) {
    return 'standalone';
  }
  return 'unknown';
};

/** 碎片率档位。1.0 与 1.5 含在正常档，4.75 落偏高。 */
export const fragmentationBand = (value: number | null | undefined): 'low' | 'ok' | 'high' | null => {
  const reading = finite(value);
  if (reading == null) return null;
  if (reading < 1) return 'low';
  if (reading > 1.5) return 'high';
  return 'ok';
};

export const replicationTabMode = ({
  hasPoint,
  pending,
  booting
}: {
  hasPoint: boolean;
  pending: boolean;
  booting: boolean;
}): ReplicationTabMode => {
  if (hasPoint) return 'ready';
  if (booting || pending) return 'loading';
  return 'gray';
};