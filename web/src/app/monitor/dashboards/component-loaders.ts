import type { ComponentType } from 'react';
import { ENTERPRISE_DASHBOARD_COMPONENT_LOADERS } from './objects/(enterprise)-loaders';
import { normalizeDashboardKey } from './shared/utils';
import { PROFESSIONAL_DASHBOARD_METADATA } from './metadata';

export type DashboardComponentLoader = () => Promise<{ default: ComponentType }>;

const COMMUNITY_DASHBOARD_COMPONENT_LOADERS: Record<string, DashboardComponentLoader> = {
  jvm: () => import('./objects/jvm'),
  mysql: () => import('./objects/mysql'),
  redis: () => import('./objects/redis'),
  mongodb: () => import('./objects/mongodb'),
  mssql: () => import('./objects/mssql'),
  nginx: () => import('./objects/nginx'),
  docker: () => import('./objects/docker'),
  activemq: () => import('./objects/activemq'),
  apache: () => import('./objects/apache'),
  consul: () => import('./objects/consul'),
  rabbitmq: () => import('./objects/rabbitmq'),
  tomcat: () => import('./objects/tomcat'),
  zookeeper: () => import('./objects/zookeeper'),
  'active-directory': () => import('./objects/active-directory'),
  exchange: () => import('./objects/exchange'),
  kafka: () => import('./objects/kafka'),
  etcd: () => import('./objects/etcd'),
  haproxy: () => import('./objects/haproxy'),
  minio: () => import('./objects/minio'),
  vllm: () => import('./objects/vllm'),
  sglang: () => import('./objects/sglang'),
  llamaserver: () => import('./objects/llamaserver'),
  postgres: () => import('./objects/postgresql'),
  elasticsearch: () => import('./objects/elasticsearch'),
  oracle: () => import('./objects/oracle'),
  influxdb: () => import('./objects/influxdb'),
  host: () => import('./objects/host'),
  process: () => import('./objects/process'),
  website: () => import('./objects/website'),
  ping: () => import('./objects/ping'),
  tcp: () => import('./objects/tcp'),
  switch: () => import('./objects/switch'),
  firewall: () => import('./objects/firewall'),
  loadbalance: () => import('./objects/loadbalance'),
  router: () => import('./objects/router'),
  netflow: () => import('./objects/netflow'),
  sflow: () => import('./objects/sflow'),
  wireless: () => import('./objects/wireless'),
  transmission: () => import('./objects/transmission'),
  access: () => import('./objects/access'),
  network_service: () => import('./objects/network_service'),
  console_server: () => import('./objects/console_server'),
  voice_gateway: () => import('./objects/voice_gateway'),
  'k8s-cluster': () => import('./objects/k8s-cluster'),
  'k8s-node': () => import('./objects/k8s-node'),
  'k8s-pod': () => import('./objects/k8s-pod'),
  'k3s-cluster': () => import('./objects/k3s-cluster'),
  'k3s-node': () => import('./objects/k3s-node'),
  'k3s-pod': () => import('./objects/k3s-pod')
};

const PRIMARY_LOADERS: Record<string, DashboardComponentLoader> = {
  ...COMMUNITY_DASHBOARD_COMPONENT_LOADERS,
  ...ENTERPRISE_DASHBOARD_COMPONENT_LOADERS
};

/** key / alias / objectName → primary key loader */
export const DASHBOARD_COMPONENT_LOADERS: Record<string, DashboardComponentLoader> = (() => {
  const map: Record<string, DashboardComponentLoader> = {};
  for (const item of PROFESSIONAL_DASHBOARD_METADATA) {
    const loader = PRIMARY_LOADERS[item.key];
    if (!loader) continue;
    const keys = [item.key, ...(item.aliases || []), item.objectName, item.objectDisplayName]
      .filter(Boolean)
      .map((key) => normalizeDashboardKey(key));
    for (const key of keys) {
      map[key] = loader;
    }
  }
  return map;
})();

export const loadDashboardComponent = async (objectKey?: string | null) => {
  const normalized = normalizeDashboardKey(objectKey);
  const loader = normalized ? DASHBOARD_COMPONENT_LOADERS[normalized] : undefined;
  if (!loader) return null;
  const mod = await loader();
  return mod.default || null;
};
