import { CONVERSATION_TOP_N, type FlowProtocol } from './constants';

const netflowBytesSeries = (instanceType: string) =>
  `netflow_in_bytes{instance_type='${instanceType}', collect_type='netflow', __$labels__}`;

const netflowPacketsSeries = (instanceType: string) =>
  `netflow_in_packets{instance_type='${instanceType}', collect_type='netflow', __$labels__}`;

const normalizedNetflowBytes = (instanceType: string) =>
  `sum(${netflowBytesSeries(instanceType)} * label_value(${netflowBytesSeries(instanceType)}, "effective_sampling_rate")) by (instance_id)`;

const normalizedNetflowPackets = (instanceType: string) =>
  `sum(${netflowPacketsSeries(instanceType)} * label_value(${netflowPacketsSeries(instanceType)}, "effective_sampling_rate")) by (instance_id)`;

const normalizedNetflowBytesByLabels = (instanceType: string, groupBy: string) =>
  `sum(${netflowBytesSeries(instanceType)} * label_value(${netflowBytesSeries(instanceType)}, "effective_sampling_rate")) by (instance_id, ${groupBy})`;

export const buildFlowCollectionStatusQuery = (instanceType: string, protocol: FlowProtocol) =>
  `any({instance_type='${instanceType}', collect_type='${protocol}'}) by (instance_id)`;

export const buildConversationTopQuery = (instanceType: string, protocol: FlowProtocol) => {
  if (protocol === 'netflow') {
    return `topk(${CONVERSATION_TOP_N}, ${normalizedNetflowBytesByLabels(instanceType, 'src, dst, protocol, dst_port')})`;
  }
  return `topk(${CONVERSATION_TOP_N}, sum(sflow_bytes{instance_type='${instanceType}', collect_type='sflow', __$labels__}) by (instance_id, src_ip, dst_ip, header_protocol, dst_port))`;
};

export const buildFlowMetricQueries = (instanceType: string, protocol: FlowProtocol) => {
  if (protocol === 'netflow') {
    return {
      device_flow_bytes_rate: normalizedNetflowBytes(instanceType),
      device_flow_packets_rate: normalizedNetflowPackets(instanceType),
      device_flow_avg_packet_size: `${normalizedNetflowBytes(instanceType)} / ${normalizedNetflowPackets(instanceType)}`,
      device_flow_effective_sampling_rate: `avg(label_value(${netflowBytesSeries(instanceType)}, "effective_sampling_rate")) by (instance_id)`,
    };
  }

  const sflowBytes = `sflow_bytes{instance_type='${instanceType}', collect_type='sflow', __$labels__}`;
  const sflowPackets = `sflow_packets{instance_type='${instanceType}', collect_type='sflow', __$labels__}`;

  return {
    device_flow_bytes_rate: `sum(${sflowBytes}) by (instance_id)`,
    device_flow_packets_rate: `sum(${sflowPackets}) by (instance_id)`,
    device_flow_avg_packet_size: `avg(sflow_frame_length{instance_type='${instanceType}', collect_type='sflow', __$labels__}) by (instance_id)`,
    device_flow_effective_sampling_rate: `avg(sflow_sampling_rate{instance_type='${instanceType}', collect_type='sflow', __$labels__}) by (instance_id) or avg(label_value(${sflowBytes}, "effective_sampling_rate")) by (instance_id)`,
  };
};
