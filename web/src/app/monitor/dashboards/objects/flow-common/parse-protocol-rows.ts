import { formatProtocolLabel } from './protocol-labels';
import type { FlowProtocol } from './constants';

interface RawSeries {
  metric?: Record<string, string>;
  value?: [number, string | number];
}

export interface FlowProtocolRow {
  protocol: string;
  label: string;
  bytesRate: number;
  rowKey: string;
}

const latestValue = (series: RawSeries): number | null => {
  const raw = series.value?.[1];
  if (raw === null || raw === undefined || raw === '') return null;
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
};

export const parseProtocolRows = (
  raw: { data?: { result?: RawSeries[] } } | null | undefined,
  flowProtocol: FlowProtocol,
): FlowProtocolRow[] => {
  const totals = new Map<string, FlowProtocolRow>();

  for (const series of raw?.data?.result || []) {
    const metric = series.metric || {};
    const bytesRate = latestValue(series);
    if (bytesRate == null) continue;

    const protocolKey = flowProtocol === 'netflow'
      ? String(metric.protocol || '').trim()
      : String(metric.header_protocol || '').trim();
    if (!protocolKey) continue;

    const existing = totals.get(protocolKey);
    if (existing) {
      existing.bytesRate += bytesRate;
      continue;
    }

    totals.set(protocolKey, {
      protocol: protocolKey,
      label: formatProtocolLabel(protocolKey),
      bytesRate,
      rowKey: protocolKey,
    });
  }

  return [...totals.values()].sort((left, right) => right.bytesRate - left.bytesRate);
};
