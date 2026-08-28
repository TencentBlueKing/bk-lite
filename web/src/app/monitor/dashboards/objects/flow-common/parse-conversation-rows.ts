import type { FlowProtocol } from './constants';
import { formatProtocolLabel } from './protocol-labels';

interface RawSeries {
  metric?: Record<string, string>;
  values?: Array<[number, string | number]>;
  value?: [number, string | number];
}

export interface ConversationQueryResult {
  data?: { result?: RawSeries[] };
}

export interface FlowConversationRow {
  srcIp: string;
  srcPort: string;
  dstIp: string;
  dstPort: string;
  protocol: string;
  bytesRate: number;
  rowKey: string;
}

const latestValue = (series: RawSeries): number | null => {
  const points: Array<[number, string | number | null | undefined]> = series.value
    ? [series.value]
    : (series.values || []);
  for (let index = points.length - 1; index >= 0; index -= 1) {
    const raw = points[index][1];
    if (raw === null || raw === undefined || raw === '') continue;
    const value = Number(raw);
    if (Number.isFinite(value)) return value;
  }
  return null;
};

const buildRowKey = (
  protocol: FlowProtocol,
  metric: Record<string, string>,
) => {
  if (protocol === 'netflow') {
    return [
      metric.src || '',
      metric.src_port || '',
      metric.dst || '',
      metric.protocol || '',
      metric.dst_port || '',
    ].join('\u0000');
  }
  return [
    metric.src_ip || '',
    metric.src_port || '',
    metric.dst_ip || '',
    metric.header_protocol || '',
    metric.dst_port || '',
  ].join('\u0000');
};

const normalizePort = (value?: string | null) => {
  const normalized = String(value || '').trim();
  return normalized || '--';
};

export const parseConversationRows = (
  raw: ConversationQueryResult | null | undefined,
  protocol: FlowProtocol,
): FlowConversationRow[] => {
  const rows: FlowConversationRow[] = [];

  for (const series of raw?.data?.result || []) {
    const metric = series.metric || {};
    const bytesRate = latestValue(series);
    if (bytesRate == null) continue;

    const rowKey = buildRowKey(protocol, metric);
    if (!rowKey.replace(/\u0000/g, '')) continue;

    if (protocol === 'netflow') {
      rows.push({
        srcIp: metric.src || '--',
        srcPort: normalizePort(metric.src_port),
        dstIp: metric.dst || '--',
        dstPort: normalizePort(metric.dst_port),
        protocol: formatProtocolLabel(metric.protocol || ''),
        bytesRate,
        rowKey,
      });
      continue;
    }

    rows.push({
      srcIp: metric.src_ip || '--',
      srcPort: normalizePort(metric.src_port),
      dstIp: metric.dst_ip || '--',
      dstPort: normalizePort(metric.dst_port),
      protocol: formatProtocolLabel(metric.header_protocol || ''),
      bytesRate,
      rowKey,
    });
  }

  return rows.sort((left, right) => right.bytesRate - left.bytesRate);
};
