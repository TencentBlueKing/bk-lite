import { MetricUnit } from '../types';

export const formatMetricValue = (value: number, unit: MetricUnit): { value: string; unit: string } => {
  if (!Number.isFinite(value)) {
    return { value: '--', unit: '' };
  }

  if (unit === 's') {
    if (value < 60) return { value: value.toFixed(0), unit: 's' };
    if (value < 3600) return { value: (value / 60).toFixed(value >= 600 ? 0 : 1), unit: 'min' };
    if (value < 86400) return { value: (value / 3600).toFixed(value >= 36000 ? 0 : 1), unit: 'h' };
    const days = Math.floor(value / 86400);
    const hours = Math.floor((value % 86400) / 3600);
    return { value: `${days}${hours > 0 ? `d ${hours}h` : 'd'}`, unit: '' };
  }

  if (unit === 'percent') return { value: value.toFixed(1), unit: '%' };
  if (unit === 'ms') return { value: value.toFixed(1), unit: 'ms' };
  if (unit === 'ns') return { value: value.toFixed(0), unit: 'ns' };
  if (unit === 'msps') return { value: value >= 100 ? value.toFixed(0) : value.toFixed(1), unit: 'ms/s' };

  if (unit === 'cps' || unit === 'ops') {
    return { value: value >= 100 ? value.toFixed(0) : value.toFixed(2), unit: '/s' };
  }

  if (unit === 'permin') {
    return { value: value >= 100 ? value.toFixed(0) : value.toFixed(1), unit: '/min' };
  }

  if (unit === 'byteps') {
    const units = ['B/s', 'KB/s', 'MB/s', 'GB/s'];
    let next = value;
    let idx = 0;
    while (next >= 1024 && idx < units.length - 1) { next /= 1024; idx += 1; }
    return { value: next >= 100 ? next.toFixed(0) : next.toFixed(1), unit: units[idx] };
  }

  if (unit === 'bytes') {
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let next = value;
    let idx = 0;
    while (next >= 1024 && idx < units.length - 1) { next /= 1024; idx += 1; }
    return { value: next >= 100 ? next.toFixed(0) : next.toFixed(1), unit: units[idx] };
  }

  if (unit === 'none') {
    return { value: value.toFixed(2).replace(/\.00$/, '').replace(/(\.\d)0$/, '$1'), unit: '' };
  }

  return {
    value: value >= 1000
      ? value.toLocaleString(undefined, { maximumFractionDigits: 0 })
      : value.toFixed(value >= 100 ? 0 : 1),
    unit: unit === 'counts' || unit === 'short' ? '' : String(unit || '')
  };
};

export const getCompareTone = (direction: 'up' | 'down' | 'flat') => {
  if (direction === 'flat') return 'flat';
  return direction === 'up' ? 'positive' : 'negative';
};
