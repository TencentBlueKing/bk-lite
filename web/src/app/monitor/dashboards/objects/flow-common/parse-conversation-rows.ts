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
  rank?: number;
}

export interface FlowConversationPageItem {
  src_ip?: string;
  dst_ip?: string;
  src_port?: string;
  dst_port?: string;
  protocol?: string;
  bytes_rate?: number;
  rank?: number;
}

export interface FlowConversationPage {
  count?: number;
  page?: number;
  page_size?: number;
  items?: FlowConversationPageItem[];
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

export const mapConversationPageItems = (
  items: FlowConversationPageItem[] | null | undefined,
): FlowConversationRow[] => {
  if (!items?.length) return [];
  return items.map((item, index) => {
    const srcIp = item.src_ip || '--';
    const dstIp = item.dst_ip || '--';
    const srcPort = normalizePort(item.src_port);
    const dstPort = normalizePort(item.dst_port);
    const protocol = item.protocol || '';
    return {
      srcIp,
      srcPort,
      dstIp,
      dstPort,
      protocol,
      bytesRate: Number(item.bytes_rate),
      rank: item.rank ?? index + 1,
      rowKey: [srcIp, srcPort, dstIp, protocol, dstPort, String(item.rank ?? index)].join('\u0000'),
    };
  }).filter((row) => Number.isFinite(row.bytesRate));
};
