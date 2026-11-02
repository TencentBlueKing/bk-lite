import {
  displayedArchitecture,
  headerRoleReading,
  inferReplicationRole,
  replicationRoleLabel,
  type ArchitectureKind,
  type RoleReading
} from './architecture-state';
import { redisLatest, redisReplicationLabels, type RedisMetricMap } from './series';

export interface RedisArchitectureView {
  kind: ArchitectureKind;
  role: RoleReading | null;
}

/** 顶栏芯片和「集群」Tab 读同一份判定，避免概览写成哨兵、复制又写成集群。 */
export const redisArchitectureView = ({
  instanceKey,
  metricMap,
  pending,
  booting
}: {
  instanceKey: string;
  metricMap: RedisMetricMap;
  pending: ReadonlySet<string>;
  booting: boolean;
}): RedisArchitectureView => {
  const labels = redisReplicationLabels(metricMap);
  const slaves = redisLatest(metricMap, 'redis_connected_slaves');
  const link = redisLatest(metricMap, 'redis_master_link_status');
  const inflight = (name: string) => booting || pending.has(name);
  const kind = displayedArchitecture(instanceKey, {
    clusterEnabled: redisLatest(metricMap, 'redis_cluster_enabled'),
    slaves,
    link,
    labeledRole: replicationRoleLabel(labels),
    clusterInflight: inflight('redis_cluster_enabled'),
    slavesInflight: inflight('redis_connected_slaves'),
    linkInflight: inflight('redis_master_link_status')
  });
  return {
    kind,
    role: headerRoleReading(inferReplicationRole({ labels, slaves, link }), kind)
  };
};
