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
 * 架构芯片。Cluster 优先。
 * 哨兵/副本只看副本连接、主从链接或副本标签。单机 INFO 的 replication_role=master 不是拓扑。
 * cluster_enabled=0、没有副本信号时判单机。其余保持未知，调用方不把未知写成「架构待识别」。
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
  const hasReplica = (slaveCount ?? 0) > 0 || linkValue != null || labeledRole === 'slave';
  if (hasReplica) return 'replica';
  if (finite(clusterEnabled) === 0 && (slaveCount ?? 0) === 0 && linkValue == null) {
    return 'standalone';
  }
  return 'unknown';
};

export interface ArchitectureSignals {
  clusterEnabled: number | null | undefined;
  slaves: number | null | undefined;
  link: number | null | undefined;
  labeledRole: 'master' | 'slave' | null;
  clusterInflight: boolean;
  slavesInflight: boolean;
  linkInflight: boolean;
}

const stickyClusterByInstance = new Map<string, boolean>();

/**
 * 顶栏和「集群」Tab 共用。
 * 集群开关还在飞时，不把已有副本连接写成哨兵。
 * 本实例见过 cluster_enabled=1 后，采样空窗继续保持集群，直到明确读到 0。
 */
export const displayedArchitecture = (
  instanceKey: string,
  input: ArchitectureSignals
): ArchitectureKind => {
  const remembered = stickyClusterByInstance.get(instanceKey) === true;
  const clusterValue = finite(input.clusterEnabled);
  const slaveCount = finite(input.slaves);
  const linkValue = finite(input.link);
  let kind: ArchitectureKind;
  if (clusterEnabledOn(input.clusterEnabled)) {
    kind = 'cluster';
  } else if (input.clusterInflight && clusterValue == null) {
    kind = remembered ? 'cluster' : 'unknown';
  } else {
    const hasReplica = (slaveCount ?? 0) > 0 || linkValue != null || input.labeledRole === 'slave';
    if (hasReplica) {
      kind = 'replica';
    } else {
      const slavesQuiet = slaveCount === 0 || (slaveCount == null && !input.slavesInflight);
      const linkQuiet = linkValue == null && !input.linkInflight;
      const clusterOff = clusterValue === 0 || (clusterValue == null && !input.clusterInflight);
      kind = clusterOff && slavesQuiet && linkQuiet ? 'standalone' : 'unknown';
    }
  }
  if (kind === 'unknown' && remembered && clusterValue !== 0) kind = 'cluster';
  if (clusterValue === 0) stickyClusterByInstance.set(instanceKey, false);
  else if (kind === 'cluster') stickyClusterByInstance.set(instanceKey, true);
  return kind;
};

/** 顶栏角色只写主节点 / 副本。更像主、更像副本收成这两档。 */
export const headerRoleReading = (
  role: RoleReading | null,
  kind: ArchitectureKind
): RoleReading | null => {
  if (kind === 'unknown') return null;
  if (role === 'replica' || role === 'lean-replica') return 'replica';
  if (role === 'mixed') return 'mixed';
  return 'primary';
};

/**
 * 容量压力档。80 起偏紧，95 起顶满。
 * 内存容量卡与复制积压条共用，避免两套阈值。
 */
export type PressureTone = 'ok' | 'near' | 'full';

export const pressureTone = (percent: number): PressureTone => {
  if (percent >= 95) return 'full';
  if (percent >= 80) return 'near';
  return 'ok';
};

/** 与容量卡同一组语义色：成功绿 / 警告橙 / 失败红。 */
export const PRESSURE_COLOR: Record<PressureTone, string> = {
  ok: 'var(--color-success)',
  near: 'var(--color-warning)',
  full: 'var(--color-fail)'
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