'use client';

import { useEffect, useState } from 'react';
import useMonitorApi from '@/app/monitor/api';
import {
  fetchDashboardInstancePages,
  resolveDashboardInstanceIdValues
} from '../../../shared/utils';
import { buildInstanceDisplayName } from '../../../shared/utils/instance';
import {
  buildHostDashboardHref,
  isHostMonitorObject,
  matchMysqlHost,
  type MysqlHostCandidate
} from './ia';

interface LinkedHostSnapshot {
  key: string;
  host: MysqlHostCandidate | null;
  phase: 'loading' | 'ready';
}

/**
 * 按节点或 IP 关联所属主机。切实例时先丢掉上一台，避免顶栏残留旧主机名。
 */
export function useMysqlLinkedHost(nodeId: string, ip: string, enabled: boolean) {
  const { getMonitorObject, getInstanceList } = useMonitorApi();
  const trimmedNodeId = nodeId.trim();
  const trimmedIp = ip.trim();
  const key = `${enabled ? '1' : '0'}|${trimmedNodeId}|${trimmedIp}`;
  const emptyLink = !enabled || (!trimmedNodeId && !trimmedIp);
  const [snapshot, setSnapshot] = useState<LinkedHostSnapshot>({
    key: '',
    host: null,
    phase: 'loading'
  });
  const aligned = snapshot.key === key;
  const phase = aligned ? snapshot.phase : (emptyLink ? 'ready' : 'loading');
  const host = aligned ? snapshot.host : null;

  useEffect(() => {
    if (aligned) return;
    setSnapshot({
      key,
      host: null,
      phase: emptyLink ? 'ready' : 'loading'
    });
  }, [aligned, emptyLink, key]);

  useEffect(() => {
    if (!enabled || (!trimmedNodeId && !trimmedIp)) return undefined;
    let active = true;
    const load = async () => {
      try {
        const objects = await getMonitorObject({ include_invisible: true });
        if (!active) return;
        if (!Array.isArray(objects)) {
          setSnapshot({ key, host: null, phase: 'ready' });
          return;
        }
        const hostObject = objects.find((item: { name?: string; display_name?: string }) => isHostMonitorObject(item));
        if (!hostObject?.id) {
          setSnapshot({ key, host: null, phase: 'ready' });
          return;
        }
        const pages = await fetchDashboardInstancePages(getInstanceList, hostObject.id);
        if (!active) return;
        const keys = Array.isArray(hostObject.instance_id_keys) && hostObject.instance_id_keys.length
          ? hostObject.instance_id_keys.map((keyName: unknown) => String(keyName))
          : ['instance_id'];
        const hosts: MysqlHostCandidate[] = (pages.results || []).map((item) => {
          const row = item as {
            instance_id?: unknown;
            node_id?: unknown;
            ip?: unknown;
            instance_id_values?: unknown;
          };
          return {
            instanceId: String(row.instance_id || ''),
            name: buildInstanceDisplayName(row),
            nodeId: String(row.node_id || '').trim(),
            ip: String(row.ip || '').trim(),
            instanceIdValues: resolveDashboardInstanceIdValues(row),
            instanceIdKeys: keys,
            monitorObjectId: String(hostObject.id)
          };
        }).filter((candidate) => candidate.instanceId);
        setSnapshot({
          key,
          host: matchMysqlHost({ nodeId: trimmedNodeId, ip: trimmedIp }, hosts),
          phase: 'ready'
        });
      } catch {
        if (active) setSnapshot({ key, host: null, phase: 'ready' });
      }
    };
    load();
    return () => {
      active = false;
    };
  }, [enabled, getInstanceList, getMonitorObject, key, trimmedIp, trimmedNodeId]);

  const pending = enabled && phase === 'loading';
  const resolved = pending ? null : host;
  return {
    host: resolved,
    href: buildHostDashboardHref(resolved),
    pending
  };
}
