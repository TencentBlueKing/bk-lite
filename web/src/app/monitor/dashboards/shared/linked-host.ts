import { normalizeDashboardKey } from './utils';
import { encodeInstanceIdValuesParam } from './utils/instance';

export interface LinkedHostCandidate {
  instanceId: string;
  name: string;
  nodeId: string;
  ip: string;
  instanceIdValues: string[];
  instanceIdKeys: string[];
  monitorObjectId: string;
}

export interface LinkedInstanceRef {
  nodeId: string;
  ip: string;
}

/** 顶栏槽位文案。有主机关联时是「所属主机」+ 名称；对不上时整段写成「无所属主机」。 */
export const LINKED_HOST_LABEL_ID = 'monitor.dashboards.text.mysqlCategoryHost';
export const LINKED_HOST_LABEL = '所属主机';
export const LINKED_HOST_UNLINKED_ID = 'monitor.dashboards.text.mysqlCategoryHostUnlinked';
export const LINKED_HOST_UNLINKED = '无所属主机';

const readableHostName = (name: string) => {
  const text = name.trim();
  return text && text !== '--' ? text : '';
};

/**
 * 只在节点或 IP 唯一命中时关联主机。对不上就不造主机名。
 */
export const matchLinkedHost = (
  instance: LinkedInstanceRef,
  hosts: readonly LinkedHostCandidate[]
): LinkedHostCandidate | null => {
  const named = hosts.filter((host) => readableHostName(host.name));
  const nodeId = instance.nodeId.trim();
  if (nodeId) {
    const byNode = named.filter((host) => host.nodeId === nodeId);
    if (byNode.length === 1) return byNode[0];
  }
  const ip = instance.ip.trim();
  if (ip) {
    const byIp = named.filter((host) => host.ip === ip);
    if (byIp.length === 1) return byIp[0];
  }
  return null;
};

const HOST_OBJECT_KEYS = ['host', 'os', '主机'];

export const isDashboardHostObject = (item: { name?: string; display_name?: string }) => {
  const name = normalizeDashboardKey(item.name);
  const displayName = normalizeDashboardKey(item.display_name);
  return HOST_OBJECT_KEYS.includes(name) || HOST_OBJECT_KEYS.includes(displayName);
};

export const buildHostDashboardHref = (host: LinkedHostCandidate | null) => {
  if (!host) return '/monitor/view/dashboard/host';
  const params = new URLSearchParams({
    monitorObjId: host.monitorObjectId,
    name: 'Host',
    monitorObjDisplayName: '主机',
    instance_id: host.instanceId,
    instance_name: host.name,
    instance_id_values: encodeInstanceIdValuesParam(host.instanceIdValues),
    instance_id_keys: host.instanceIdKeys.join(',') || 'instance_id'
  });
  return `/monitor/view/dashboard/host?${params.toString()}`;
};
