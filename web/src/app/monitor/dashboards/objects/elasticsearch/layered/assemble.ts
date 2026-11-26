import { formatMetricValue } from '@/app/monitor/dashboards/shared/utils/format';
import type { MetricUnit } from '@/app/monitor/dashboards/shared/types';
import type { EsMetricId } from '../queries';
import { ES_HINT, type EsHint } from './copy';
import {
  aggregateClusterHealth,
  alignSamples,
  capabilityFromSamples,
  collectionFace,
  collectionLabel,
  freshNumbers,
  freshWindowSeconds,
  healthLabel,
  healthTone,
  heapBand,
  labelIdentity,
  type AlignedSample,
  type CollectionFace,
  type EsFormat,
  type FreshNumber,
  type HealthCode
} from './model';
import { clockText, foldNodeNames } from './names';
import {
  newestEvalTime,
  type InstantOutcome,
  type InstantPoint,
  type RangeLine,
  type RangeOutcome
} from './wire';

export type { EsFormat } from './model';
export type { EsHint } from './copy';

export type EsTabId = 'overview' | 'nodes' | 'queues';
export type CardStatus = 'loading' | 'error' | 'empty' | 'value';
export type EsTone = 'success' | 'warning' | 'fail';

export interface EsBag {
  pending: boolean;
  hasInstance: boolean;
  nowSeconds: number;
  freshSeconds: number;
  instant: Record<string, InstantOutcome>;
  range: Record<string, RangeOutcome>;
  alertCount: number | null;
  alertPending: boolean;
}

export interface EsKpi {
  id: string;
  title: string;
  unit: string;
  hint: EsHint;
  status: CardStatus;
  value: string;
  note: string;
  tone?: EsTone;
  dot?: 'green' | 'yellow' | 'red';
  emptyText: string;
  opensAlerts?: boolean;
}

export interface EsFocus {
  id: string;
  title: string;
  hint: EsHint;
  status: CardStatus;
  primary: string;
  secondary: string;
  tone?: EsTone;
  emptyText: string;
  target: 'nodes' | 'queues';
}

export interface EsRankRow {
  id: string;
  label: string;
  fullName: string;
  value: number | null;
  text: string;
  stale: boolean;
  sourceClock: string;
  tone?: EsTone;
}

export interface EsRank {
  id: string;
  title: string;
  unit: string;
  hint: EsHint;
  status: CardStatus;
  emptyText: string;
  rows: EsRankRow[];
  allZero: boolean;
  full: number;
  single: boolean;
}

export interface EsSeries {
  id: string;
  label: string;
  fullName: string;
  points: Array<{ time: number; value: number }>;
  average: number;
}

export interface EsTrend {
  id: string;
  title: string;
  unit: string;
  metricUnit: MetricUnit;
  hint: EsHint;
  status: CardStatus;
  emptyText: string;
  series: EsSeries[];
  curve: 'linear' | 'step';
  kind: 'line' | 'bar';
  stacked?: boolean;
  valueBounds?: { min: number; max: number };
  references?: number[];
  integerAxis?: boolean;
  zeroOverlay?: string;
  liftZero?: boolean;
  readings?: EsRankRow[];
}

export interface EsStat {
  id: string;
  title: string;
  hint: EsHint;
  status: CardStatus;
  emptyText: string;
  figures: Array<{ label: string; value: string; tone?: EsTone }>;
  note: string;
}

export interface EsView {
  pending: boolean;
  healthLabel: string;
  healthTone: 'green' | 'yellow' | 'red' | 'unknown';
  collectionLabel: string;
  tabs: Array<{ id: EsTabId; title: string }>;
  kpis: EsKpi[];
  focuses: EsFocus[];
  httpOpen: EsTrend;
  httpRate: EsTrend;
  heap: EsTrend;
  ranks: EsRank[];
  writeRate: EsTrend;
  gc: EsTrend;
  queueStat: EsStat;
  breakerStat: EsStat;
  queueTrend: EsTrend;
  breakerTrend: EsTrend;
  retry: () => void;
}

const NO_RETRY = () => undefined;

const BYTE_SCALE = [
  { unit: 'TiB', size: 1024 ** 4 },
  { unit: 'GiB', size: 1024 ** 3 },
  { unit: 'MiB', size: 1024 ** 2 },
  { unit: 'KiB', size: 1024 },
  { unit: 'B', size: 1 }
] as const;

const RATE_SCALE = [
  { unit: 'TiB/s', size: 1024 ** 4 },
  { unit: 'GiB/s', size: 1024 ** 3 },
  { unit: 'MiB/s', size: 1024 ** 2 },
  { unit: 'KiB/s', size: 1024 },
  { unit: 'B/s', size: 1 }
] as const;

const metricUnitOf = (format: EsFormat): MetricUnit => {
  if (format === 'bytes') return 'bytes';
  if (format === 'byteps') return 'byteps';
  if (format === 'cps') return 'cps';
  if (format === 'msps') return 'msps';
  if (format === 'counts') return 'counts';
  return 'percent';
};

const tidy = (text: string) => text.replace(/\.0$/, '');

export const readingParts = (value: number, format: EsFormat, anchor = value): { text: string; unit: string } => {
  if (!Number.isFinite(value)) return { text: '—', unit: '' };
  if (format === 'counts') {
    const shown = Math.abs(value - Math.round(value)) < 0.05 ? Math.round(value) : value;
    if (shown === 0) return { text: '0', unit: '' };
    return { text: formatMetricValue(shown, 'counts').value, unit: '' };
  }
  if (format === 'bytes' || format === 'byteps') {
    const table = format === 'bytes' ? BYTE_SCALE : RATE_SCALE;
    const basis = Math.max(Math.abs(anchor), Math.abs(value));
    const step = table.find((item) => basis >= item.size) ?? table[table.length - 1];
    if (value === 0) return { text: '0', unit: step.unit };
    const scaled = value / step.size;
    const text = Math.abs(scaled) >= 100 ? scaled.toFixed(0) : tidy(scaled.toFixed(1));
    return { text, unit: step.unit };
  }
  if (value === 0) {
    if (format === 'percent') return { text: '0', unit: '%' };
    if (format === 'msps') return { text: '0', unit: 'ms/s' };
    return { text: '0', unit: '/秒' };
  }
  const formatted = formatMetricValue(value, metricUnitOf(format));
  const unit = formatted.unit === '/s' ? '/秒' : formatted.unit;
  return { text: tidy(formatted.value), unit };
};

export const axisNumber = (value: number, integer = false): string => {
  if (!Number.isFinite(value)) return '';
  if (integer) return String(Math.max(0, Math.round(value)));
  const abs = Math.abs(value);
  if (abs >= 100 || Number.isInteger(value)) return tidy(value.toFixed(abs >= 100 ? 0 : 1));
  if (abs >= 10) return tidy(value.toFixed(1));
  return value.toFixed(2).replace(/\.00$/, '').replace(/(\.\d)0$/, '$1');
};

const okInstant = (outcome: InstantOutcome | undefined): InstantPoint[] => (
  outcome?.kind === 'ok' ? outcome.series : []
);

const okRange = (outcome: RangeOutcome | undefined): RangeLine[] => (
  outcome?.kind === 'ok' ? outcome.series : []
);

type QueryState = 'loading' | 'error' | 'ok';

const instantState = (bag: EsBag, key: string): QueryState => {
  if (bag.pending) return 'loading';
  const outcome = bag.instant[key];
  if (!outcome || outcome.kind === 'loading') return 'loading';
  if (outcome.kind === 'error') return 'error';
  return 'ok';
};

const rangeState = (bag: EsBag, key: string): QueryState => {
  if (bag.pending) return 'loading';
  const outcome = bag.range[key];
  if (!outcome || outcome.kind === 'loading') return 'loading';
  if (outcome.kind === 'error') return 'error';
  return 'ok';
};

const combine = (...states: QueryState[]): CardStatus => {
  if (states.some((state) => state === 'loading')) return 'loading';
  if (states.some((state) => state === 'error')) return 'error';
  return 'value';
};

type CapabilityState = 'loading' | 'error' | 'absent' | 'present';

const metricCapability = (bag: EsBag, id: EsMetricId): CapabilityState => {
  if (bag.pending) return 'loading';
  const outcome = bag.instant[`cap:${id}`];
  if (!outcome) return 'absent';
  if (outcome.kind === 'loading') return 'loading';
  if (outcome.kind === 'error') return 'error';
  return capabilityFromSamples(outcome.series.map((series) => series.sample), bag.nowSeconds);
};

const tabVisible = (bag: EsBag, ids: readonly EsMetricId[]): boolean => {
  if (bag.pending) return true;
  return ids.some((id) => {
    const state = metricCapability(bag, id);
    return state === 'present' || state === 'error' || state === 'loading';
  });
};

const alignedGauge = (bag: EsBag, id: EsMetricId): AlignedSample[] => (
  alignSamples(okInstant(bag.instant[`val:${id}`]), okInstant(bag.instant[`src:${id}`]))
);

interface NodePoint {
  label: string;
  value: number;
  sourceTime: number | null;
  stale: boolean;
}

const collapseFresh = (rows: readonly FreshNumber[], how: 'max' | 'min'): FreshNumber[] => {
  const by = new Map<string, FreshNumber>();
  rows.forEach((row) => {
    const key = row.label || '';
    if (!key) return;
    const prev = by.get(key);
    if (!prev) {
      by.set(key, row);
      return;
    }
    const better = how === 'max' ? row.value > prev.value : row.value < prev.value;
    if (better || (row.value === prev.value && row.sourceTime > prev.sourceTime)) by.set(key, row);
  });
  return [...by.values()];
};

const gaugeNodes = (bag: EsBag, id: EsMetricId, how: 'max' | 'min'): NodePoint[] => {
  const aligned = alignedGauge(bag, id);
  const fresh = collapseFresh(freshNumbers(aligned, bag.nowSeconds, bag.freshSeconds), how);
  const freshNames = new Set(fresh.map((row) => row.label).filter(Boolean));
  const stale = new Map<string, { value: number | null; sourceTime: number | null }>();
  aligned.forEach((row) => {
    const name = row.labels.node_name;
    if (!name || freshNames.has(name)) return;
    const prev = stale.get(name);
    if (!prev || ((row.sourceTime ?? 0) > (prev.sourceTime ?? 0))) {
      stale.set(name, { value: row.value, sourceTime: row.sourceTime });
    }
  });
  return [
    ...fresh.map((row) => ({
      label: row.label || '',
      value: row.value,
      sourceTime: row.sourceTime,
      stale: false
    })),
    ...[...stale.entries()].map(([label, row]) => ({
      label,
      value: row.value ?? 0,
      sourceTime: row.sourceTime,
      stale: true
    }))
  ].filter((row) => row.label);
};

const sortNodes = (rows: readonly NodePoint[], direction: 'desc' | 'asc'): NodePoint[] => {
  const live = rows.filter((row) => !row.stale);
  const stale = rows.filter((row) => row.stale);
  live.sort((left, right) => {
    const byValue = direction === 'desc' ? right.value - left.value : left.value - right.value;
    return byValue || left.label.localeCompare(right.label);
  });
  stale.sort((left, right) => left.label.localeCompare(right.label));
  return [...live, ...stale];
};

const cpuNodes = (bag: EsBag): NodePoint[] => {
  const by = new Map<string, { value: number; time: number }>();
  okRange(bag.range.cpuRateNodes).forEach((line) => {
    const label = line.labels.node_name || '';
    if (!label) return;
    let last: { time: number; value: number } | null = null;
    line.points.forEach((point) => {
      if (!Number.isFinite(point.value)) return;
      if (!last || point.time >= last.time) last = point;
    });
    if (!last) return;
    const prev = by.get(label);
    if (!prev || last.value > prev.value) by.set(label, last);
  });
  return [...by.entries()].map(([label, point]) => ({
    label,
    value: point.value,
    sourceTime: point.time,
    stale: false
  }));
};

const namesOf = (labels: readonly string[]) => foldNodeNames(labels);

const showNode = (count: number) => count > 1;

const emptyTextFor = (cap: CapabilityState, hadSamples: boolean): string => {
  if (cap === 'absent') return '尚未接入采集';
  if (hadSamples) return '最近 20 分钟没有新的读数';
  return '暂无数据';
};

const kpi = (
  partial: Omit<EsKpi, 'status' | 'value' | 'note' | 'emptyText'> & {
    status: CardStatus;
    value?: string;
    note?: string;
    emptyText?: string;
  }
): EsKpi => ({
  value: '',
  note: '',
  emptyText: '暂无数据',
  ...partial
});

const rankRows = (
  rows: readonly NodePoint[],
  format: EsFormat,
  toneFor?: (value: number) => EsTone | undefined
): { rows: EsRankRow[]; unit: string; full: number; allZero: boolean; single: boolean } => {
  const live = rows.filter((row) => !row.stale);
  const anchor = live.reduce((best, row) => Math.max(best, Math.abs(row.value)), 0);
  const unit = live.length ? readingParts(anchor || live[0].value, format, anchor || live[0].value).unit : readingParts(0, format).unit;
  const mapped = rows.map((row) => {
    const parts = readingParts(row.value, format, anchor || row.value);
    return {
      id: row.label,
      label: '',
      fullName: row.label,
      value: row.stale ? null : row.value,
      text: row.stale ? '—' : parts.text,
      stale: row.stale,
      sourceClock: clockText(row.sourceTime, true),
      tone: !row.stale && toneFor ? toneFor(row.value) : undefined
    } satisfies EsRankRow;
  });
  const folded = namesOf(mapped.map((row) => row.fullName));
  mapped.forEach((row) => {
    row.label = folded.get(row.fullName) || row.fullName;
  });
  const full = format === 'percent' ? Math.max(100, anchor) : Math.max(anchor, 0);
  return {
    rows: mapped,
    unit,
    full,
    allZero: live.length > 0 && live.every((row) => row.value === 0),
    single: live.length === 1
  };
};

const seriesFrom = (lines: readonly RangeLine[], labels: readonly string[]): EsSeries[] => {
  const folded = namesOf(lines.map((line, index) => line.labels.node_name || labels[index] || '集群'));
  return lines.map((line, index) => {
    const fullName = line.labels.node_name || labels[index] || '集群';
    const points = line.points.filter((point) => Number.isFinite(point.value));
    const average = points.length
      ? points.reduce((total, point) => total + point.value, 0) / points.length
      : 0;
    return {
      id: line.labels.node_name || labelIdentity(line.labels) || fullName,
      label: folded.get(fullName) || fullName,
      fullName,
      points,
      average
    };
  });
};

const lastOf = (series: EsSeries | undefined): number | null => {
  if (!series) return null;
  for (let index = series.points.length - 1; index >= 0; index -= 1) {
    const value = series.points[index]?.value;
    if (typeof value === 'number' && Number.isFinite(value)) return value;
  }
  return null;
};

const peakOf = (series: EsSeries | undefined): number | null => {
  if (!series?.points.length) return null;
  return series.points.reduce((best, point) => Math.max(best, point.value), Number.NEGATIVE_INFINITY);
};

const sumInstant = (bag: EsBag, key: string): number | null => {
  const rows = okInstant(bag.instant[key]).map((series) => series.sample).filter((value): value is number => (
    typeof value === 'number' && Number.isFinite(value)
  ));
  if (!rows.length) return null;
  return rows.reduce((total, value) => total + value, 0);
};

const blankTrend = (
  id: string,
  title: string,
  hint: EsHint,
  metricUnit: MetricUnit,
  curve: EsTrend['curve'],
  kind: EsTrend['kind']
): EsTrend => ({
  id,
  title,
  unit: '',
  metricUnit,
  hint,
  status: 'loading',
  emptyText: '暂无数据',
  series: [],
  curve,
  kind
});

const HEALTH_NOTE: Record<HealthCode, string> = {
  1: '主分片和副本都已分配',
  2: '主分片都已分配，仍有副本未分配',
  3: '至少一块主分片没有分配'
};

const heapTone = (value: number): EsTone => {
  const band = heapBand(value);
  if (band === '充足') return 'success';
  if (band === '接近') return 'warning';
  return 'fail';
};

const countText = (value: number | null): string => (
  value == null ? '—' : readingParts(value, 'counts').text
);

export const wallClockSeconds = (instants: Record<string, InstantOutcome>, fallbackNow: number): number => {
  const samples: InstantPoint[] = [];
  Object.values(instants).forEach((outcome) => {
    if (outcome.kind === 'ok') samples.push(...outcome.series);
  });
  return newestEvalTime(samples) ?? fallbackNow;
};

export const assembleElasticsearch = (bag: EsBag): EsView => {
  const healthCap = metricCapability(bag, 'health');
  const healthQuery = instantState(bag, 'val:health');
  const healthSamples = alignedGauge(bag, 'health');
  const health = healthQuery === 'ok'
    ? aggregateClusterHealth(healthSamples, bag.nowSeconds, bag.freshSeconds)
    : null;
  const healthCode: HealthCode | null = health?.kind === 'value' ? health.code : null;
  const successTimes = okInstant(bag.instant['src:health']).map((series) => series.sample);
  const collection: CollectionFace = bag.pending
    ? { kind: 'unknown' }
    : collectionFace({
      hasInstance: bag.hasInstance,
      successTimes,
      failTimes: [],
      nowSeconds: bag.nowSeconds,
      freshSeconds: bag.freshSeconds
    });

  const heapRows = sortNodes(gaugeNodes(bag, 'heap', 'max'), 'desc');
  const diskRows = sortNodes(gaugeNodes(bag, 'disk', 'min'), 'asc');
  const fdRows = sortNodes(gaugeNodes(bag, 'fd', 'max'), 'desc');
  const deletedRows = sortNodes(gaugeNodes(bag, 'deleted', 'max'), 'desc');
  const unassignedRows = gaugeNodes(bag, 'unassigned', 'max');
  const primaryRows = gaugeNodes(bag, 'primary', 'max');
  const writeRows = sortNodes(gaugeNodes(bag, 'writeQueue', 'max'), 'desc');
  const searchRows = sortNodes(gaugeNodes(bag, 'searchQueue', 'max'), 'desc');
  const cpu = sortNodes(cpuNodes(bag), 'desc');
  const cpuState = rangeState(bag, 'cpuRateNodes');

  const live = (rows: readonly NodePoint[]) => rows.filter((row) => !row.stale);
  const tightest = (rows: readonly NodePoint[]) => live(rows)[0] ?? null;
  const noteName = (row: NodePoint | null, rows: readonly NodePoint[]) => (
    row && showNode(rows.length) ? (namesOf(rows.map((item) => item.label)).get(row.label) || row.label) : ''
  );

  const gaugeKpi = (
    id: string,
    title: string,
    hint: EsHint,
    metric: EsMetricId,
    rows: readonly NodePoint[],
    format: EsFormat,
    pick: NodePoint | null,
    note: string,
    tone?: EsTone
  ): EsKpi => {
    const status = combine(instantState(bag, `val:${metric}`), instantState(bag, `src:${metric}`));
    if (status !== 'value') {
      return kpi({ id, title, unit: readingParts(0, format).unit, hint, status, emptyText: '暂无数据' });
    }
    const cap = metricCapability(bag, metric);
    if (!pick) {
      return kpi({
        id,
        title,
        unit: readingParts(0, format).unit,
        hint,
        status: 'empty',
        emptyText: emptyTextFor(cap, rows.some((row) => row.stale) || cap === 'present')
      });
    }
    const parts = readingParts(pick.value, format, Math.max(...live(rows).map((row) => Math.abs(row.value)), Math.abs(pick.value)));
    return kpi({
      id,
      title,
      unit: parts.unit,
      hint,
      status: 'value',
      value: parts.text,
      note,
      tone
    });
  };

  const healthCard = (): EsKpi => {
    const status = combine(healthQuery, instantState(bag, 'src:health'));
    if (status !== 'value') return kpi({ id: 'health', title: '集群健康', unit: '', hint: ES_HINT.health, status });
    if (healthCap === 'absent') {
      return kpi({ id: 'health', title: '集群健康', unit: '', hint: ES_HINT.health, status: 'empty', emptyText: '尚未接入采集' });
    }
    if (!healthCode) {
      return kpi({
        id: 'health',
        title: '集群健康',
        unit: '',
        hint: ES_HINT.health,
        status: 'value',
        value: '—',
        note: '最近 20 分钟没有新的读数'
      });
    }
    const tone = healthTone(healthCode);
    return kpi({
      id: 'health',
      title: '集群健康',
      unit: '',
      hint: ES_HINT.health,
      status: 'value',
      value: healthLabel(healthCode),
      note: HEALTH_NOTE[healthCode],
      dot: tone === 'unknown' ? undefined : tone,
      tone: healthCode === 1 ? 'success' : healthCode === 2 ? 'warning' : 'fail'
    });
  };

  const countKpi = (
    id: string,
    title: string,
    hint: EsHint,
    metric: EsMetricId,
    rows: readonly NodePoint[]
  ): EsKpi => {
    const pick = live(rows).reduce<NodePoint | null>(
      (best, row) => (!best || row.value > best.value ? row : best),
      null
    );
    const card = gaugeKpi(id, title, hint, metric, rows, 'counts', pick, pick ? `最近读数 ${clockText(pick.sourceTime)}` : '');
    if (card.status === 'value' && pick && pick.value > 0 && id === 'unassigned') card.tone = 'fail';
    return card;
  };

  const heapPick = tightest(heapRows);
  const diskPick = tightest(diskRows);
  const fdPick = tightest(fdRows);
  const cpuPick = tightest(cpu);
  const cpuAllZero = live(cpu).length > 0 && live(cpu).every((row) => row.value === 0);
  const cpuCard = (): EsKpi => {
    if (cpuState !== 'ok') {
      return kpi({ id: 'cpu', title: '进程 CPU', unit: '%', hint: ES_HINT.cpu, status: cpuState === 'error' ? 'error' : 'loading' });
    }
    if (!cpuPick) {
      const cap = metricCapability(bag, 'cpu');
      return kpi({
        id: 'cpu',
        title: '进程 CPU',
        unit: '%',
        hint: ES_HINT.cpu,
        status: 'empty',
        emptyText: cap === 'absent' ? '尚未接入采集' : '暂无数据'
      });
    }
    const parts = readingParts(cpuPick.value, 'percent');
    return kpi({
      id: 'cpu',
      title: '进程 CPU',
      unit: '%',
      hint: ES_HINT.cpu,
      status: 'value',
      value: parts.text,
      note: cpuAllZero ? '各节点均为 0' : noteName(cpuPick, cpu)
    });
  };

  const alertCard = (): EsKpi => {
    if (bag.alertPending || bag.pending) {
      return kpi({ id: 'alerts', title: '告警数量', unit: '', hint: ES_HINT.alerts, status: 'loading', opensAlerts: true });
    }
    if (bag.alertCount == null) {
      return kpi({ id: 'alerts', title: '告警数量', unit: '', hint: ES_HINT.alerts, status: 'empty', emptyText: '暂无数据', opensAlerts: true });
    }
    const count = Math.max(0, Math.round(bag.alertCount));
    return kpi({
      id: 'alerts',
      title: '告警数量',
      unit: '',
      hint: ES_HINT.alerts,
      status: 'value',
      value: String(count),
      note: '点击查看',
      tone: count > 0 ? 'fail' : undefined,
      opensAlerts: true
    });
  };

  const kpis = [
    healthCard(),
    countKpi('unassigned', '未分配分片', ES_HINT.unassigned, 'unassigned', unassignedRows),
    countKpi('primary', '活跃主分片', ES_HINT.primary, 'primary', primaryRows),
    alertCard(),
    gaugeKpi('heap', 'JVM 堆使用率', ES_HINT.heap, 'heap', heapRows, 'percent', heapPick, heapPick ? [heapBand(heapPick.value), noteName(heapPick, heapRows)].filter(Boolean).join(' · ') : '', heapPick ? heapTone(heapPick.value) : undefined),
    cpuCard(),
    gaugeKpi('disk', '节点可用磁盘', ES_HINT.disk, 'disk', diskRows, 'bytes', diskPick, noteName(diskPick, diskRows)),
    gaugeKpi('fd', '打开文件描述符', ES_HINT.fd, 'fd', fdRows, 'counts', fdPick, noteName(fdPick, fdRows))
  ];

  const clusterPick = (rows: readonly NodePoint[]) => live(rows).reduce<NodePoint | null>(
    (best, row) => (!best || row.value > best.value ? row : best),
    null
  );
  const unassignedPick = clusterPick(unassignedRows);
  const primaryPick = clusterPick(primaryRows);
  const focusStatus = (states: QueryState[]): CardStatus => combine(...states);

  const shardFocus = (): EsFocus => {
    const status = focusStatus([
      healthQuery,
      instantState(bag, 'val:unassigned'),
      instantState(bag, 'val:primary')
    ]);
    return {
      id: 'shards',
      title: '分片是否全部就位',
      hint: ES_HINT.shards,
      status,
      emptyText: '暂无数据',
      target: 'nodes',
      tone: healthCode === 1 ? 'success' : healthCode === 2 ? 'warning' : healthCode === 3 ? 'fail' : undefined,
      primary: status === 'value' ? (healthCode ? healthLabel(healthCode) : '—') : '',
      secondary: status === 'value'
        ? `未分配 ${countText(unassignedPick?.value ?? null)} · 活跃主分片 ${countText(primaryPick?.value ?? null)}`
        : ''
    };
  };

  const gcSeries = seriesFrom(okRange(bag.range.gcNodes), []);
  const gcState = rangeState(bag, 'gcNodes');
  const gcBest = [...gcSeries].sort((left, right) => (lastOf(right) ?? -1) - (lastOf(left) ?? -1))[0];
  const gcLast = lastOf(gcBest);
  const pressureFocus = (): EsFocus => {
    const status = focusStatus([instantState(bag, 'val:heap'), gcState]);
    const heapParts = heapPick ? readingParts(heapPick.value, 'percent') : null;
    let secondary = '';
    if (status === 'value') {
      if (gcState !== 'ok' || gcLast == null) secondary = 'GC 暂无数据';
      else {
        const parts = readingParts(gcLast, 'msps');
        const who = gcBest && showNode(gcSeries.length) ? ` · ${gcBest.label}` : '';
        secondary = `年轻代 GC 最高 ${parts.text} ${parts.unit}${who}`;
      }
    }
    return {
      id: 'pressure',
      title: 'JVM 是否承压',
      hint: ES_HINT.pressure,
      status,
      emptyText: '暂无数据',
      target: 'nodes',
      tone: heapPick ? heapTone(heapPick.value) : undefined,
      primary: status === 'value'
        ? (heapPick && heapParts ? `${heapParts.text}${heapParts.unit} ${heapBand(heapPick.value)}` : '—')
        : '',
      secondary
    };
  };

  const writePick = live(writeRows)[0] ?? null;
  const searchPick = live(searchRows)[0] ?? null;
  const breakerKeys = ['breakerField', 'breakerRequest', 'breakerParent'] as const;
  const breakerStates = breakerKeys.map((key) => instantState(bag, key));
  const breakerValues = breakerKeys.map((key) => sumInstant(bag, key));
  const breakerTotal = breakerValues.every((value) => value == null)
    ? null
    : breakerValues.reduce((total, value) => total + (value ?? 0), 0);
  const blockedFocus = (): EsFocus => {
    const status = focusStatus([
      instantState(bag, 'val:writeQueue'),
      instantState(bag, 'val:searchQueue'),
      ...breakerStates
    ]);
    return {
      id: 'blocked',
      title: '请求是否被挡',
      hint: ES_HINT.blocked,
      status,
      emptyText: '暂无数据',
      target: 'queues',
      primary: status === 'value'
        ? `写入排队 ${countText(writePick?.value ?? null)} · 搜索排队 ${countText(searchPick?.value ?? null)}`
        : '',
      secondary: status === 'value' ? `熔断 ${countText(breakerTotal)} 次（这段时间）` : ''
    };
  };

  const trendOf = (
    id: string,
    title: string,
    hint: EsHint,
    key: string,
    format: EsFormat,
    curve: EsTrend['curve'],
    kind: EsTrend['kind'],
    caps: CapabilityState,
    labels: readonly string[] = [],
    extra: Partial<EsTrend> = {}
  ): EsTrend => {
    const status = rangeState(bag, key);
    const series = status === 'ok' ? seriesFrom(okRange(bag.range[key]), labels) : [];
    const anchor = series.reduce((best, item) => Math.max(best, ...item.points.map((point) => Math.abs(point.value)), 0), 0);
    const unit = readingParts(anchor, format).unit;
    const plotted = series.some((item) => item.points.length > 0);
    if (status !== 'ok') {
      return { ...blankTrend(id, title, hint, metricUnitOf(format), curve, kind), status: status === 'error' ? 'error' : 'loading', ...extra };
    }
    if (!plotted) {
      return {
        ...blankTrend(id, title, hint, metricUnitOf(format), curve, kind),
        status: 'empty',
        unit,
        emptyText: emptyTextFor(caps, false),
        ...extra
      };
    }
    const allZero = series.every((item) => item.points.every((point) => point.value === 0));
    return {
      id,
      title,
      unit,
      metricUnit: metricUnitOf(format),
      hint,
      status: 'value',
      emptyText: '暂无数据',
      series,
      curve,
      kind,
      liftZero: kind === 'line',
      zeroOverlay: kind === 'bar' && allZero ? '这段时间没有触发' : undefined,
      ...extra
    };
  };

  const httpOpen = trendOf('http-open', 'HTTP 当前连接', ES_HINT.httpOpen, 'httpOpenAgg', 'counts', 'step', 'line', metricCapability(bag, 'httpOpen'), ['当前连接'], { integerAxis: true });
  const httpRate = trendOf('http-rate', 'HTTP 新建连接速率', ES_HINT.httpRate, 'httpRateAgg', 'cps', 'linear', 'line', metricCapability(bag, 'httpOpened'), ['新建连接']);
  const heapCap = metricCapability(bag, 'heap');
  const heapSeries = trendOf('heap-nodes', 'JVM 堆使用率 · 各节点', ES_HINT.heapNodes, 'heapNodes', 'percent', 'linear', 'line', heapCap, [], {
    valueBounds: { min: 0, max: 100 },
    references: [75, 85],
    unit: '%'
  });
  const heapRank = rankRows(heapRows, 'percent', heapTone);
  heapSeries.readings = heapRank.rows;
  if (rangeState(bag, 'heapNodes') === 'ok' && instantState(bag, 'val:heap') === 'ok') {
    const hasLine = heapSeries.series.some((item) => item.points.length > 0);
    const hasReading = heapRank.rows.some((row) => !row.stale);
    heapSeries.status = hasLine || hasReading ? 'value' : 'empty';
  }

  const rankOf = (
    id: string,
    title: string,
    hint: EsHint,
    metric: EsMetricId | 'cpu',
    rows: readonly NodePoint[],
    format: EsFormat,
    state: CardStatus
  ): EsRank => {
    const built = rankRows(rows, format, metric === 'heap' ? heapTone : undefined);
    return {
      id,
      title,
      unit: built.unit,
      hint,
      status: state,
      emptyText: state === 'value' && !rows.length
        ? emptyTextFor(metric === 'cpu' ? metricCapability(bag, 'cpu') : metricCapability(bag, metric), false)
        : '暂无数据',
      rows: built.rows,
      allZero: built.allZero,
      full: built.full,
      single: built.single
    };
  };

  const ranks: EsRank[] = [
    rankOf('cpu-rank', '进程 CPU 排行', ES_HINT.cpuRank, 'cpu', cpu, 'percent', cpuState === 'ok' ? (cpu.length ? 'value' : 'empty') : cpuState === 'error' ? 'error' : 'loading'),
    rankOf('disk-rank', '节点可用磁盘排行', ES_HINT.diskRank, 'disk', diskRows, 'bytes', combine(instantState(bag, 'val:disk'), instantState(bag, 'src:disk')) === 'value' ? (diskRows.length ? 'value' : 'empty') : combine(instantState(bag, 'val:disk'), instantState(bag, 'src:disk'))),
    rankOf('fd-rank', '打开文件描述符排行', ES_HINT.fdRank, 'fd', fdRows, 'counts', combine(instantState(bag, 'val:fd'), instantState(bag, 'src:fd')) === 'value' ? (fdRows.length ? 'value' : 'empty') : combine(instantState(bag, 'val:fd'), instantState(bag, 'src:fd'))),
    rankOf('deleted-rank', '未合并删除文档排行', ES_HINT.deletedRank, 'deleted', deletedRows, 'counts', combine(instantState(bag, 'val:deleted'), instantState(bag, 'src:deleted')) === 'value' ? (deletedRows.length ? 'value' : 'empty') : combine(instantState(bag, 'val:deleted'), instantState(bag, 'src:deleted')))
  ];

  const writeRate = trendOf('write-rate', '节点磁盘写入速率 · 各节点', ES_HINT.write, 'writeNodes', 'byteps', 'linear', 'line', metricCapability(bag, 'write'));
  const gc = trendOf('gc', '年轻代 GC 耗时 · 各节点', ES_HINT.gc, 'gcNodes', 'msps', 'linear', 'line', metricCapability(bag, 'gc'));

  const queueSeries = {
    write: seriesFrom(okRange(bag.range.writeQueueAgg), ['写入']),
    search: seriesFrom(okRange(bag.range.searchQueueAgg), ['搜索'])
  };
  const queueStat = (): EsStat => {
    const status = focusStatus([
      instantState(bag, 'val:writeQueue'),
      instantState(bag, 'val:searchQueue'),
      rangeState(bag, 'writeQueueAgg'),
      rangeState(bag, 'searchQueueAgg')
    ]);
    const writePeak = peakOf(queueSeries.write[0]);
    const searchPeak = peakOf(queueSeries.search[0]);
    const named = (writePick && writePick.value > 0) || (searchPick && searchPick.value > 0);
    const folded = namesOf([writePick?.label, searchPick?.label].filter((name): name is string => Boolean(name)));
    const note = named
      ? [
        writePick && writePick.value > 0 ? `写入 ${folded.get(writePick.label) || writePick.label}` : '',
        searchPick && searchPick.value > 0 ? `搜索 ${folded.get(searchPick.label) || searchPick.label}` : ''
      ].filter(Boolean).join(' · ')
      : `这段时间最高 写入 ${countText(writePeak)} · 搜索 ${countText(searchPeak)}`;
    return {
      id: 'queues',
      title: '线程池队列',
      hint: ES_HINT.queues,
      status,
      emptyText: '暂无数据',
      figures: [
        { label: '写入', value: countText(writePick ? writePick.value : null) },
        { label: '搜索', value: countText(searchPick ? searchPick.value : null) }
      ],
      note: status === 'value' ? note : ''
    };
  };

  const breakerLabels = ['Fielddata', '请求', '父级'] as const;
  const breakerStat = (): EsStat => {
    const status = focusStatus([...breakerStates]);
    return {
      id: 'breakers',
      title: '熔断触发',
      hint: ES_HINT.breakers,
      status,
      emptyText: '暂无数据',
      figures: breakerLabels.map((label, index) => ({
        label,
        value: countText(status === 'value' ? (breakerValues[index] ?? 0) : null)
      })),
      note: status === 'value' ? '这段时间内次数，各节点相加' : ''
    };
  };

  const queueTrend = trendOf(
    'queue-trend',
    '线程池队列趋势',
    ES_HINT.queueTrend,
    'writeQueueAgg',
    'counts',
    'step',
    'line',
    metricCapability(bag, 'writeQueue'),
    ['写入']
  );
  if (rangeState(bag, 'searchQueueAgg') === 'error') queueTrend.status = 'error';
  else if (rangeState(bag, 'writeQueueAgg') === 'ok') {
    const search = seriesFrom(okRange(bag.range.searchQueueAgg), ['搜索']);
    queueTrend.series = [...queueTrend.series, ...search];
    if (queueTrend.series.some((item) => item.points.length > 0)) queueTrend.status = 'value';
  }
  queueTrend.integerAxis = true;
  queueTrend.liftZero = true;

  const breakerTrend = trendOf(
    'breaker-trend',
    '熔断触发 · 每步次数',
    ES_HINT.breakerTrend,
    'breakerFieldStep',
    'counts',
    'linear',
    'bar',
    metricCapability(bag, 'breakerField'),
    ['Fielddata'],
    { stacked: true, integerAxis: true }
  );
  if (['breakerRequestStep', 'breakerParentStep'].some((key) => rangeState(bag, key) === 'error')) {
    breakerTrend.status = 'error';
  } else if (rangeState(bag, 'breakerFieldStep') === 'ok') {
    const rest = [
      ...seriesFrom(okRange(bag.range.breakerRequestStep), ['请求']),
      ...seriesFrom(okRange(bag.range.breakerParentStep), ['父级'])
    ];
    breakerTrend.series = [...breakerTrend.series, ...rest];
    const plotted = breakerTrend.series.some((item) => item.points.length > 0);
    const allZero = plotted && breakerTrend.series.every((item) => item.points.every((point) => point.value === 0));
    breakerTrend.status = plotted ? 'value' : 'empty';
    breakerTrend.zeroOverlay = allZero ? '这段时间没有触发' : undefined;
    breakerTrend.stacked = true;
    breakerTrend.integerAxis = true;
  }

  const nodeIds: EsMetricId[] = ['heap', 'cpu', 'disk', 'fd', 'deleted', 'write', 'gc'];
  const queueIds: EsMetricId[] = ['writeQueue', 'searchQueue', 'breakerField', 'breakerRequest', 'breakerParent'];
  const tabs: EsView['tabs'] = [{ id: 'overview', title: '概览' }];
  if (tabVisible(bag, nodeIds)) tabs.push({ id: 'nodes', title: '节点与资源' });
  if (tabVisible(bag, queueIds)) tabs.push({ id: 'queues', title: '队列与熔断' });

  return {
    pending: bag.pending,
    healthLabel: bag.pending ? '' : healthLabel(healthCode),
    healthTone: bag.pending ? 'unknown' : healthTone(healthCode),
    collectionLabel: bag.pending ? '' : collectionLabel(collection.kind === 'unknown' && !bag.hasInstance ? { kind: 'not-attached' } : collection),
    tabs,
    kpis,
    focuses: [shardFocus(), pressureFocus(), blockedFocus()],
    httpOpen,
    httpRate,
    heap: heapSeries,
    ranks,
    writeRate,
    gc,
    queueStat: queueStat(),
    breakerStat: breakerStat(),
    queueTrend,
    breakerTrend,
    retry: NO_RETRY
  };
};

const emptyBag = (partial: Pick<EsBag, 'pending' | 'hasInstance' | 'nowSeconds' | 'freshSeconds' | 'alertCount' | 'alertPending'>): EsBag => ({
  ...partial,
  instant: {},
  range: {}
});

export const pendingElasticsearchView = (): EsView => assembleElasticsearch(emptyBag({
  pending: true,
  hasInstance: false,
  nowSeconds: 0,
  freshSeconds: freshWindowSeconds(null),
  alertCount: null,
  alertPending: true
}));
