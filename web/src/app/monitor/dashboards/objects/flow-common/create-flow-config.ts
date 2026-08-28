import type { SimpleDashboardConfig } from '../common/simple-dashboard-core';
import type { FlowProtocol } from './constants';
import { buildFlowCollectionStatusQuery, buildFlowMetricQueries } from './queries';

export interface CreateFlowDashboardConfigOptions {
  protocol: FlowProtocol;
  instanceType: string;
  objectFallbackName?: string;
  objectDisplayName?: string;
}

export const createFlowDashboardConfig = ({
  protocol,
  instanceType,
  objectFallbackName = 'Switch',
  objectDisplayName,
}: CreateFlowDashboardConfigOptions): SimpleDashboardConfig => {
  const queries = buildFlowMetricQueries(instanceType, protocol);
  const protocolLabel = protocol === 'netflow' ? 'NetFlow' : 'sFlow';
  const objectLabel = objectDisplayName || objectFallbackName;

  return {
    routeKey: protocol,
    pageTitle: `${protocolLabel} 流量分析`,
    objectFallbackName,
    instanceType,
    collectionStatusQuery: buildFlowCollectionStatusQuery(instanceType, protocol),
    metaItems: ['Telegraf', protocol],
    metrics: [
      {
        name: 'device_flow_bytes_rate',
        display_name: '总流量速率',
        description: `${protocolLabel} 设备总流量速率。`,
        unit: 'byteps',
        query: queries.device_flow_bytes_rate,
        color: '#2f6bff',
      },
      {
        name: 'device_flow_packets_rate',
        display_name: '总包速率',
        description: `${protocolLabel} 设备总包速率。`,
        unit: 'pps',
        query: queries.device_flow_packets_rate,
        color: '#13c2c2',
      },
      {
        name: 'device_flow_avg_packet_size',
        display_name: '平均包大小',
        description: `${protocolLabel} 平均包大小。`,
        unit: 'bytes',
        query: queries.device_flow_avg_packet_size,
        color: '#722ed1',
      },
      {
        name: 'device_flow_effective_sampling_rate',
        display_name: '有效采样率',
        description: `${protocolLabel} 有效采样率，用于流量归一化。`,
        unit: 'none',
        query: queries.device_flow_effective_sampling_rate,
        color: '#27c274',
      },
    ],
    summaryCards: [
      {
        title: '总流量速率',
        metric: 'device_flow_bytes_rate',
        unit: 'byteps',
        color: '#2f6bff',
        icon: 'thunder',
        compare: true,
        guide: [{ label: '总流量', detail: `${objectLabel} 的 ${protocolLabel} 总流量速率。` }],
      },
      {
        title: '总包速率',
        metric: 'device_flow_packets_rate',
        unit: 'pps',
        color: '#13c2c2',
        icon: 'thunder',
        compare: true,
        guide: [{ label: '总包速率', detail: `${objectLabel} 的 ${protocolLabel} 总包速率。` }],
      },
      {
        title: '平均包大小',
        metric: 'device_flow_avg_packet_size',
        unit: 'bytes',
        color: '#722ed1',
        icon: 'database',
        compare: true,
        guide: [{ label: '平均包大小', detail: '反映当前流量以大包还是小包为主。' }],
      },
      {
        title: '有效采样率',
        metric: 'device_flow_effective_sampling_rate',
        unit: 'none',
        color: '#27c274',
        icon: 'health',
        compare: true,
        formatter: 'samplingRate',
        guide: [{ label: '采样率', detail: '表示约每 N 个包采样 1 个；采样率未生效时总流量可能为估算值。' }],
      },
    ],
    charts: [],
    ringPanels: [],
    barPanels: [],
    statusPanels: [],
    details: [],
  };
};
