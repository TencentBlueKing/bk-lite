import type { Key } from 'react';
import type { FlowDashboardPlugin } from '@/app/monitor/dashboards/shared/utils/flow-dashboard-route';
import {
  getAvailableFlowViews,
  isSnmpPlugin,
} from '@/app/monitor/dashboards/shared/utils/flow-view-navigation';
import { isFlowSupportedObjectName } from '@/app/monitor/dashboards/objects/flow-common/constants';
import type { SearchParams } from '@/app/monitor/types/search';
import { isMonitorViewDemoEnabled } from './monitor-view-demo-data';

const nowSeconds = () => Math.floor(Date.now() / 1000);

const buildValues = (base: number, unit = 'none') => {
  const end = nowSeconds();
  const step = 60;
  return Array.from({ length: 36 }, (_, index) => {
    const wave = Math.sin(index / 4) * base * 0.08;
    const drift = Math.cos(index / 7) * base * 0.04;
    const value = Math.max(unit === 'percent' ? 0 : 0.01, base + wave + drift);
    return [end - (35 - index) * step, value.toFixed(unit === 'none' ? 0 : 2)] as [number, string];
  });
};

const unescapePromRegexValue = (value: string) =>
  value.replace(/\\\\/g, '\\').replace(/\\([\\^$.*+?()[\]{}|"-])/g, '$1');

const parseInstanceIdFromQuery = (query = '') => {
  const matcher = /instance_id=~"([^"]+)"/.exec(query);
  if (!matcher?.[1]) return 'demo-switch';
  return unescapePromRegexValue(matcher[1]).split('|')[0] || 'demo-switch';
};

const parseInstanceTypeFromQuery = (query = '') => {
  const matcher = /instance_type='([^']+)'/.exec(query);
  return matcher?.[1] || 'switch';
};

const inferFlowBaseValue = (query = '', unit = 'none') => {
  const isSflow = query.includes('sflow');
  const scale = isSflow ? 0.88 : 1;
  if (query.includes('netflow_in_bytes') || query.includes('sflow_bytes')) {
    return (unit === 'byteps' ? 420 * 1024 : 420 * 1024) * scale;
  }
  if (query.includes('netflow_in_packets') || query.includes('sflow_packets')) {
    return (unit === 'cps' ? 860 : 860) * scale;
  }
  if (query.includes('sflow_frame_length')) return 512 * scale;
  if (query.includes('effective_sampling_rate') || query.includes('sflow_sampling_rate')) {
    return isSflow ? 8192 : 1000;
  }
  if (query.includes('collect_type=') && query.includes('any(')) return 1;
  if (unit === 'byteps') return 320 * 1024 * scale;
  if (unit === 'cps') return 420 * scale;
  if (unit === 'bytes') return 512 * scale;
  if (unit === 'none') return isSflow ? 8192 : 1000;
  return 42 * scale;
};

export const isFlowMetricQuery = (query = '') =>
  query.includes("collect_type='netflow'")
  || query.includes('collect_type="netflow"')
  || query.includes("collect_type='sflow'")
  || query.includes('collect_type="sflow"')
  || query.includes('netflow_in_bytes')
  || query.includes('netflow_in_packets')
  || query.includes('sflow_bytes')
  || query.includes('sflow_packets')
  || query.includes('sflow_frame_length')
  || query.includes('sflow_sampling_rate')
  || (query.includes('topk(') && (query.includes('src_ip') || query.includes('src, dst')));

const isEmptyMetricResult = (response: unknown) => {
  const data = (response as { data?: { result?: unknown[] } } | null)?.data;
  return !Array.isArray(data?.result) || data.result.length === 0;
};

const metricSeries = (
  metric: Record<string, string>,
  base: number,
  unit: string,
) => ({
  metric,
  values: buildValues(base, unit),
});

const instantSeries = (
  metric: Record<string, string>,
  base: number,
) => ({
  metric,
  value: [nowSeconds(), base.toFixed(2)] as [number, string],
});

const buildFlowConversationInstant = (query = '', unit = 'byteps') => {
  const instanceId = parseInstanceIdFromQuery(query);
  const instanceType = parseInstanceTypeFromQuery(query);
  const isSflow = query.includes('src_ip');
  const baseLabels = {
    instance_id: instanceId,
    instance_type: instanceType,
    collect_type: isSflow ? 'sflow' : 'netflow',
  };
  const rows = isSflow
    ? [
      { src: '10.20.30.12', dst: '10.20.40.88', protocol: '6', dst_port: '443', rate: 1 },
      { src: '10.20.30.15', dst: '10.20.40.20', protocol: '17', dst_port: '53', rate: 0.82 },
      { src: '10.20.30.21', dst: '10.20.40.99', protocol: '6', dst_port: '8080', rate: 0.64 },
      { src: '10.20.30.33', dst: '10.20.40.44', protocol: '1', dst_port: '0', rate: 0.41 },
      { src: '10.20.30.55', dst: '10.20.40.66', protocol: '6', dst_port: '22', rate: 0.28 },
      { src: '10.20.30.61', dst: '10.20.40.72', protocol: '17', dst_port: '123', rate: 0.24 },
      { src: '10.20.30.77', dst: '10.20.40.81', protocol: '6', dst_port: '3306', rate: 0.19 },
      { src: '10.20.30.88', dst: '10.20.40.92', protocol: '6', dst_port: '443', rate: 0.16 },
      { src: '10.20.30.91', dst: '10.20.40.11', protocol: '17', dst_port: '161', rate: 0.12 },
      { src: '10.20.30.95', dst: '10.20.40.18', protocol: '6', dst_port: '80', rate: 0.09 },
    ]
    : [
      { src: '10.10.20.12', dst: '10.10.30.88', protocol: '6', dst_port: '443', rate: 1 },
      { src: '10.10.20.15', dst: '10.10.30.20', protocol: '17', dst_port: '53', rate: 0.82 },
      { src: '10.10.20.21', dst: '10.10.30.99', protocol: '6', dst_port: '8080', rate: 0.64 },
      { src: '10.10.20.33', dst: '10.10.30.44', protocol: '1', dst_port: '0', rate: 0.41 },
      { src: '10.10.20.55', dst: '10.10.30.66', protocol: '6', dst_port: '22', rate: 0.28 },
      { src: '10.10.20.61', dst: '10.10.30.72', protocol: '17', dst_port: '123', rate: 0.24 },
      { src: '10.10.20.77', dst: '10.10.30.81', protocol: '6', dst_port: '3306', rate: 0.19 },
      { src: '10.10.20.88', dst: '10.10.30.92', protocol: '6', dst_port: '443', rate: 0.16 },
      { src: '10.10.20.91', dst: '10.10.30.11', protocol: '17', dst_port: '161', rate: 0.12 },
      { src: '10.10.20.95', dst: '10.10.30.18', protocol: '6', dst_port: '80', rate: 0.09 },
    ];

  return {
    data: {
      result: rows.map((row, index) =>
        instantSeries(
          isSflow
            ? {
              ...baseLabels,
              src_ip: row.src,
              dst_ip: row.dst,
              header_protocol: row.protocol,
              dst_port: row.dst_port,
            }
            : {
              ...baseLabels,
              src: row.src,
              dst: row.dst,
              protocol: row.protocol,
              dst_port: row.dst_port,
            },
          inferFlowBaseValue(query, unit) * row.rate * (1 - index * 0.03),
        ),
      ),
    },
  };
};

const buildFlowQueryRangeResponse = (
  params: Pick<SearchParams, 'query' | 'source_unit'>,
) => {
  const query = String(params.query || '');
  const unit = String(params.source_unit || 'none');
  const instanceId = parseInstanceIdFromQuery(query);
  const instanceType = parseInstanceTypeFromQuery(query);
  const collectType = query.includes('sflow') ? 'sflow' : 'netflow';

  return {
    data: {
      result: [
        metricSeries(
          {
            instance_id: instanceId,
            instance_type: instanceType,
            collect_type: collectType,
          },
          inferFlowBaseValue(query, unit),
          unit,
        ),
      ],
    },
  };
};

export const maybeMockFlowQueryRange = <T>(
  params: SearchParams,
  response: T,
): T => {
  if (!isMonitorViewDemoEnabled()) return response;

  const query = String(params.query || '');
  if (!isFlowMetricQuery(query)) return response;
  if (!isEmptyMetricResult(response)) return response;

  return buildFlowQueryRangeResponse(params) as T;
};

const DEMO_FLOW_PLUGINS = [
  { collect_type: 'snmp_generic', name: 'SNMP' },
  { collect_type: 'netflow', name: 'NetFlow' },
  { collect_type: 'sflow', name: 'sFlow' },
] satisfies FlowDashboardPlugin[];

const hasCollectType = (plugins: FlowDashboardPlugin[], collectType: string) =>
  plugins.some((plugin) => String(plugin.collect_type || '').trim() === collectType);

const hasFlowRelatedPlugin = (plugins: FlowDashboardPlugin[]) =>
  plugins.some(
    (plugin) =>
      isSnmpPlugin(plugin)
      || String(plugin.collect_type || '').trim() === 'netflow'
      || String(plugin.collect_type || '').trim() === 'sflow',
  );

const normalizeMonitorPlugins = (payload: unknown): Array<Record<string, unknown>> => {
  if (Array.isArray(payload)) return payload;
  if (typeof payload === 'object' && payload !== null) {
    const record = payload as { items?: unknown[]; results?: unknown[] };
    if (Array.isArray(record.items)) return record.items as Array<Record<string, unknown>>;
    if (Array.isArray(record.results)) return record.results as Array<Record<string, unknown>>;
  }
  return [];
};

/** 开发演示：用监控对象已注册插件补齐 NetFlow/sFlow 页签（必须有真实 plugin id）。 */
export const enrichDemoFlowEffectivePlugins = async <T>(
  objectId: Key | undefined,
  response: T,
  loadObjectPlugins: () => Promise<unknown>,
): Promise<T> => {
  if (!isMonitorViewDemoEnabled() || !objectId || !Array.isArray(response)) return response;

  const effective = response as FlowDashboardPlugin[];
  if (!hasFlowRelatedPlugin(effective)) return response;

  try {
    const registry = normalizeMonitorPlugins(await loadObjectPlugins());
    const merged: FlowDashboardPlugin[] = [...effective];

    for (const collectType of ['netflow', 'sflow'] as const) {
      if (hasCollectType(merged, collectType)) continue;
      const registryPlugin = registry.find(
        (item) => String(item.collect_type || '').trim() === collectType && item.id != null,
      );
      if (!registryPlugin) continue;
      merged.push({
        ...(registryPlugin as FlowDashboardPlugin),
        collect_type: collectType,
        name: String(registryPlugin.name || collectType),
      });
    }

    return merged as T;
  } catch {
    return response;
  }
};

const mergeDemoFlowPlugins = (plugins: FlowDashboardPlugin[]): FlowDashboardPlugin[] => {
  const merged = [...plugins];
  for (const demoPlugin of DEMO_FLOW_PLUGINS) {
    const collectType = String(demoPlugin.collect_type || '').trim();
    if (collectType === 'snmp_generic') {
      if (!merged.some(isSnmpPlugin)) merged.push(demoPlugin);
      continue;
    }
    if (!hasCollectType(merged, collectType)) {
      merged.push(demoPlugin);
    }
  }
  return merged;
};

/** Flow 切换条：mock 模式下在 Flow 语境中补齐插件，加载中也可展示完整选项。 */
export const resolveFlowViewSwitchPlugins = (
  plugins: FlowDashboardPlugin[] | null,
  options: { routeKey: string; monitorObjectName?: string | null },
): FlowDashboardPlugin[] => {
  const routeKey = String(options.routeKey || '').trim();
  const inFlowContext =
    routeKey === 'netflow'
    || routeKey === 'sflow'
    || isFlowSupportedObjectName(options.monitorObjectName);

  if (!inFlowContext) return plugins ?? [];

  if (!isMonitorViewDemoEnabled()) return plugins ?? [];

  const base = plugins ?? [];
  const seed = base.length > 0
    ? base
    : [{
      collect_type: routeKey === 'netflow' ? 'netflow' : 'sflow',
      name: routeKey === 'netflow' ? 'NetFlow' : 'sFlow',
    }];
  const merged = mergeDemoFlowPlugins(
    hasFlowRelatedPlugin(seed as FlowDashboardPlugin[])
      ? (seed as FlowDashboardPlugin[])
      : [...(seed as FlowDashboardPlugin[]), { collect_type: 'sflow', name: 'sFlow' }],
  );
  return getAvailableFlowViews(merged).length >= 2 ? merged : mergeDemoFlowPlugins(DEMO_FLOW_PLUGINS);
};

export const maybeMockFlowInstantQuery = <T>(
  params: SearchParams,
  response: T,
): T => {
  if (!isMonitorViewDemoEnabled()) return response;

  const query = String(params.query || '');
  if (!isFlowMetricQuery(query)) return response;
  if (!isEmptyMetricResult(response)) return response;

  if (query.includes('topk(') && (query.includes('src_ip') || query.includes('src, dst'))) {
    return buildFlowConversationInstant(query, String(params.source_unit || 'byteps')) as T;
  }

  const instanceId = parseInstanceIdFromQuery(query);
  const instanceType = parseInstanceTypeFromQuery(query);
  const unit = String(params.source_unit || 'none');
  const collectType = query.includes('sflow') ? 'sflow' : 'netflow';

  return {
    data: {
      result: [
        instantSeries(
          {
            instance_id: instanceId,
            instance_type: instanceType,
            collect_type: collectType,
          },
          inferFlowBaseValue(query, unit),
        ),
      ],
    },
  } as T;
};
