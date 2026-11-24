import { formatMetricValue } from '@/app/monitor/dashboards/shared/utils/format';
import type { MetricUnit } from '@/app/monitor/dashboards/shared/types';
import type { EsMetricId } from '../queries';
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
  latestFresh,
  maxFresh,
  minFresh,
  type AlignedSample,
  type CollectionFace,
  type EsFormat,
  type FreshNumber,
  type HealthCode
} from './model';
import {
  newestEvalTime,
  type InstantOutcome,
  type InstantPoint,
  type RangeLine,
  type RangeOutcome
} from './wire';

export type { EsFormat } from './model';

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

export interface EsOverviewCard {
  id: string;
  title: string;
  hintTitle: string;
  hintBody: string;
  state: 'loading' | 'empty' | 'value';
  value: string;
  note: string;
  tone?: 'success' | 'warning' | 'fail';
  opensAlerts?: boolean;
}

export interface EsLineModel {
  id: string;
  label: string;
  fresh: boolean;
  reading: string;
  points: Array<{ time: number; value: number }>;
}

export interface EsChartModel {
  id: string;
  title: string;
  hintTitle: string;
  hintBody: string;
  format: EsFormat;
  state: 'loading' | 'empty' | 'value';
  lines: EsLineModel[];
  pinZero: boolean;
}

export type EsTabId = 'overview' | 'nodes' | 'throughput' | 'breakers';

export interface EsView {
  pending: boolean;
  healthLabel: string;
  healthTone: 'green' | 'yellow' | 'red' | 'unknown';
  collectionLabel: string;
  tabs: Array<{ id: EsTabId; title: string }>;
  overview: EsOverviewCard[];
  nodes: EsChartModel[];
  throughput: EsChartModel[];
  breakers: EsChartModel[];
}

const HINT = {
  health: '当前集群的整体健康。\n绿色\n主分片和副本都已分配。\n黄色\n主分片都已分配，但仍有副本未分配，数据可以访问，冗余不足。\n红色\n至少有一块主分片尚未分配，部分数据无法读写。\n暂无数据\n还没有采到可识别、仍然新鲜的健康状态时显示 —。',
  unassigned: '尚未分配到节点的分片个数，包含主分片和副本。\n为 0\n当前没有待分配分片，属于正常。\n大于 0\n有分片还没落到节点。可到「节点与资源」查看磁盘是否紧张。',
  primary: '当前处于活跃状态的主分片个数。用来看主分片规模，不是分配百分比。',
  heap: '当前 JVM 堆内存已用占比。多节点时本卡展示最高的那一个节点，节点名写在脚注。\n充足\n低于 75%。\n接近\n75% 到 85%，两端都算在内。\n高压\n高于 85%。持续高压时，垃圾回收会更频繁，集群更容易卡顿。',
  cpu: 'Elasticsearch 进程占用的 CPU。按逻辑核累计，多核机器上可以超过 100%，并不表示已经超过整机上限。多节点时本卡展示最高的那一个节点。',
  disk: '数据目录当前还能写入的空间。对应节点的第一块数据路径，不是主机所有磁盘之和。多节点时本卡展示剩余空间最少的节点。',
  alerts: '当前对象相关的告警条数，可打开告警列表。',
  fd: '进程已打开的文件描述符数量。',
  write: '节点每秒写入磁盘的数据量。持续偏高常见于批量索引或段合并。',
  deleted: '已经标记删除、但还没有通过段合并回收的文档个数。数值为 0 表示没有这类积压，属于正常。',
  writeQueue: '批量写入请求正在排队的数量。本图展示各节点中的最大值。为 0 表示写入没有积压。',
  searchQueue: '搜索请求正在排队的数量。本图展示各节点中的最大值。为 0 表示搜索没有积压。',
  httpOpen: '各节点当前仍打开的 HTTP 连接数之和。',
  httpRate: '这段时间里每秒新打开的 HTTP 连接数之和。用来看出连接是否突然变多，不是已经打开的连接总数。',
  field: 'Fielddata 内存保护被触发的速率，为各节点之和。为 0 表示这段时间没有触发。',
  request: '请求级内存保护被触发的速率，为各节点之和。为 0 表示这段时间没有触发。',
  parent: '节点整体内存记账触顶而被拒绝的速率，为各节点之和。为 0 表示这段时间没有触发。',
  gc: '这段时间内年轻代垃圾回收耗时的平均速率，单位是毫秒/秒。升高表示回收占用的时间在增加，不是单次停顿的毫秒数。'
} as const;

export const formatEsValue = (value: number, format: EsFormat): string => {
  if (!Number.isFinite(value)) return '—';
  if (value === 0) {
    switch (format) {
      case 'percent':
        return '0%';
      case 'counts':
        return '0个';
      case 'bytes':
        return '0 Bytes';
      case 'byteps':
        return '0 Bytes/s';
      case 'cps':
        return '0个/秒';
      case 'msps':
        return '0 ms/s';
      default: {
        const exhaustive: never = format;
        return exhaustive;
      }
    }
  }
  const unit: MetricUnit = format === 'counts'
    ? 'counts'
    : format === 'bytes'
      ? 'bytes'
      : format === 'byteps'
        ? 'byteps'
        : format === 'cps'
          ? 'cps'
          : format === 'msps'
            ? 'msps'
            : 'percent';
  const formatted = formatMetricValue(value, unit);
  if (format === 'counts') return `${formatted.value}${formatted.unit}个`;
  if (format === 'cps') return `${formatted.value}个/秒`;
  if (format === 'percent') return `${formatted.value}%`;
  return `${formatted.value} ${formatted.unit}`.trim();
};

const okInstant = (outcome: InstantOutcome | undefined): InstantPoint[] => (
  outcome?.kind === 'ok' ? outcome.series : []
);

const okRange = (outcome: RangeOutcome | undefined): RangeLine[] => (
  outcome?.kind === 'ok' ? outcome.series : []
);

type CapabilityState = 'loading' | 'error' | 'absent' | 'present';

const metricCapability = (bag: EsBag, id: EsMetricId): CapabilityState => {
  if (bag.pending) return 'loading';
  const outcome = bag.instant[`cap:${id}`];
  if (!outcome) return 'absent';
  if (outcome.kind === 'loading') return 'loading';
  if (outcome.kind === 'error') return 'error';
  return capabilityFromSamples(outcome.series.map((series) => series.sample), bag.nowSeconds);
};

const showCard = (state: CapabilityState): boolean => state === 'loading' || state === 'error' || state === 'present';

const alignedGauge = (bag: EsBag, id: EsMetricId): AlignedSample[] => (
  alignSamples(okInstant(bag.instant[`val:${id}`]), okInstant(bag.instant[`src:${id}`]))
);

const gaugeFresh = (bag: EsBag, id: EsMetricId): FreshNumber[] => (
  freshNumbers(alignedGauge(bag, id), bag.nowSeconds, bag.freshSeconds)
);

const anyFreshSource = (bag: EsBag, id: EsMetricId): boolean => {
  const times = okInstant(bag.instant[`src:${id}`]);
  return times.some((series) => (
    series.sample != null
    && series.sample >= 1e9
    && series.sample <= bag.nowSeconds + 5
    && bag.nowSeconds - series.sample <= bag.freshSeconds
  ));
};

const nodeCount = (bag: EsBag, id: EsMetricId): number => {
  const names = new Set<string>();
  okInstant(bag.instant[`cap:${id}`]).forEach((series) => {
    if (series.sample == null || !Number.isFinite(series.sample)) return;
    names.add(series.labels.node_name || labelIdentity(series.labels));
  });
  return names.size;
};

const lastPointValue = (points: readonly { value: number }[]): number | null => {
  if (!points.length) return null;
  const value = points[points.length - 1]?.value;
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
};

const overviewCard = (
  id: string,
  title: string,
  hintTitle: string,
  hintBody: string,
  state: CapabilityState,
  reading: FreshNumber | null,
  format: EsFormat,
  note = '',
  tone?: EsOverviewCard['tone']
): EsOverviewCard | null => {
  if (!showCard(state)) return null;
  if (state === 'loading') {
    return { id, title, hintTitle, hintBody, state: 'loading', value: '', note: '' };
  }
  if (!reading) {
    return { id, title, hintTitle, hintBody, state: 'empty', value: '—', note: '' };
  }
  return {
    id,
    title,
    hintTitle,
    hintBody,
    state: 'value',
    value: formatEsValue(reading.value, format),
    note,
    tone
  };
};

const heapTone = (percent: number): EsOverviewCard['tone'] => {
  const band = heapBand(percent);
  if (band === '充足') return 'success';
  if (band === '接近') return 'warning';
  return 'fail';
};

const lineFromRange = (
  series: RangeLine,
  fresh: boolean,
  reading: number | null,
  format: EsFormat,
  fallbackLabel: string
): EsLineModel => {
  const label = series.labels.node_name || fallbackLabel;
  return {
    id: labelIdentity(series.labels) || label,
    label,
    fresh,
    reading: fresh && reading != null ? formatEsValue(reading, format) : '—',
    points: fresh ? series.points : []
  };
};

const nodeLines = (
  bag: EsBag,
  id: EsMetricId,
  rangeKey: string,
  format: EsFormat,
  gauge: boolean
): EsLineModel[] => {
  const freshMap = new Map<string, FreshNumber>();
  if (gauge) {
    gaugeFresh(bag, id).forEach((row) => {
      const key = row.label || '';
      if (key) freshMap.set(key, row);
    });
  }
  const freshNames = new Set<string>();
  okInstant(bag.instant[`src:${id}`]).forEach((series) => {
    const sample = series.sample;
    if (sample == null) return;
    if (sample < 1e9 || sample > bag.nowSeconds + 5) return;
    if (bag.nowSeconds - sample > bag.freshSeconds) return;
    if (series.labels.node_name) freshNames.add(series.labels.node_name);
  });
  return okRange(bag.range[rangeKey]).map((series) => {
    const node = series.labels.node_name || '';
    const fresh = node ? freshNames.has(node) : anyFreshSource(bag, id);
    const gaugeReading = node ? freshMap.get(node) : undefined;
    const reading = gauge
      ? (gaugeReading?.value ?? null)
      : lastPointValue(series.points);
    return lineFromRange(series, fresh, fresh ? reading : null, format, '集群');
  });
};

const chartFromLines = (
  id: string,
  title: string,
  hintTitle: string,
  hintBody: string,
  format: EsFormat,
  pinZero: boolean,
  capability: CapabilityState,
  lines: EsLineModel[]
): EsChartModel | null => {
  if (capability === 'absent') return null;
  if (capability === 'loading') {
    return { id, title, hintTitle, hintBody, format, pinZero, state: 'loading', lines: [] };
  }
  const plotted = lines.some((line) => line.fresh && line.points.length > 0);
  const hasReading = lines.some((line) => line.fresh && line.reading !== '—');
  if (!plotted && !hasReading) {
    return { id, title, hintTitle, hintBody, format, pinZero, state: 'empty', lines };
  }
  return { id, title, hintTitle, hintBody, format, pinZero, state: 'value', lines };
};

const singleAggChart = (
  bag: EsBag,
  id: string,
  title: string,
  hintTitle: string,
  hintBody: string,
  format: EsFormat,
  pinZero: boolean,
  metricIds: readonly EsMetricId[],
  rangeKeys: readonly string[],
  labels: readonly string[]
): EsChartModel | null => {
  const states = metricIds.map((metricId) => metricCapability(bag, metricId));
  if (states.every((state) => state === 'absent')) return null;
  if (states.some((state) => state === 'loading')) {
    return { id, title, hintTitle, hintBody, format, pinZero, state: 'loading', lines: [] };
  }
  const lines = rangeKeys.map((rangeKey, index) => {
    const metricId = metricIds[index];
    const state = states[index];
    if (state === 'absent' || !metricId) return null;
    const series = okRange(bag.range[rangeKey])[0];
    const fresh = anyFreshSource(bag, metricId);
    const reading = fresh && series ? lastPointValue(series.points) : null;
    if (!series) {
      return {
        id: rangeKey,
        label: labels[index] || rangeKey,
        fresh,
        reading: '—',
        points: []
      } satisfies EsLineModel;
    }
    return {
      ...lineFromRange(series, fresh, reading, format, labels[index] || '集群'),
      id: rangeKey,
      label: labels[index] || series.labels.node_name || '集群'
    };
  }).filter((line): line is EsLineModel => line != null);
  const usable = lines.filter((line) => line.fresh && (line.points.length > 0 || line.reading !== '—'));
  if (!usable.length) {
    return { id, title, hintTitle, hintBody, format, pinZero, state: 'empty', lines };
  }
  return { id, title, hintTitle, hintBody, format, pinZero, state: 'value', lines };
};

const emptyBag = (partial: Pick<EsBag, 'pending' | 'hasInstance' | 'nowSeconds' | 'freshSeconds' | 'alertCount' | 'alertPending'>): EsBag => ({
  ...partial,
  instant: {},
  range: {}
});

export const wallClockSeconds = (instants: Record<string, InstantOutcome>, fallbackNow: number): number => {
  const samples: InstantPoint[] = [];
  Object.values(instants).forEach((outcome) => {
    if (outcome.kind === 'ok') samples.push(...outcome.series);
  });
  return newestEvalTime(samples) ?? fallbackNow;
};

export const assembleElasticsearch = (bag: EsBag): EsView => {
  const healthState = metricCapability(bag, 'health');
  const healthSamples = alignedGauge(bag, 'health');
  const health = healthState === 'loading'
    ? null
    : aggregateClusterHealth(healthSamples, bag.nowSeconds, bag.freshSeconds);
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

  const heap = maxFresh(gaugeFresh(bag, 'heap'));
  const cpu = maxFresh(gaugeFresh(bag, 'cpu'));
  const disk = minFresh(gaugeFresh(bag, 'disk'));
  const unassigned = latestFresh(gaugeFresh(bag, 'unassigned'));
  const primary = latestFresh(gaugeFresh(bag, 'primary'));

  const overview: EsOverviewCard[] = [];
  overview.push({
    id: 'alerts',
    title: '告警数量',
    hintTitle: '告警数量',
    hintBody: HINT.alerts,
    state: bag.alertPending ? 'loading' : bag.alertCount == null ? 'empty' : 'value',
    value: bag.alertCount == null ? '—' : String(Math.max(0, Math.round(bag.alertCount))),
    note: '',
    tone: bag.alertCount != null && bag.alertCount > 0 ? 'fail' : bag.alertCount === 0 ? 'success' : undefined,
    opensAlerts: true
  });
  const healthCard = overviewCard(
    'health',
    '集群健康',
    '集群健康',
    HINT.health,
    healthState,
    health?.kind === 'value' ? { value: health.code, sourceTime: health.sourceTime } : null,
    'counts'
  );
  if (healthCard && healthCard.state === 'value') {
    overview.push({
      ...healthCard,
      value: healthLabel(healthCode),
      tone: healthCode === 1 ? 'success' : healthCode === 2 ? 'warning' : healthCode === 3 ? 'fail' : undefined
    });
  } else if (healthCard) overview.push(healthCard);
  [
    overviewCard('unassigned', '未分配分片', '未分配分片', HINT.unassigned, metricCapability(bag, 'unassigned'), unassigned, 'counts', '', unassigned && unassigned.value > 0 ? 'fail' : unassigned ? 'success' : undefined),
    overviewCard('primary', '活跃主分片数', '活跃主分片数', HINT.primary, metricCapability(bag, 'primary'), primary, 'counts'),
    overviewCard('heap', 'JVM 堆使用率', 'JVM 堆使用率', HINT.heap, metricCapability(bag, 'heap'), heap, 'percent', heap ? `${heapBand(heap.value)}${heap.label ? ` · ${heap.label}` : ''}` : '', heap ? heapTone(heap.value) : undefined),
    overviewCard('cpu', '进程 CPU', '进程 CPU', HINT.cpu, metricCapability(bag, 'cpu'), cpu, 'percent', cpu?.label || ''),
    overviewCard('disk', '节点可用磁盘', '节点可用磁盘', HINT.disk, metricCapability(bag, 'disk'), disk, 'bytes', disk?.label || '')
  ].forEach((card) => {
    if (card) overview.push(card);
  });

  const nodeChart = (
    id: string,
    title: string,
    hintTitle: string,
    hintBody: string,
    metricId: EsMetricId,
    rangeKey: string,
    format: EsFormat,
    pinZero: boolean,
    gauge: boolean
  ) => chartFromLines(
    id,
    title,
    hintTitle,
    hintBody,
    format,
    pinZero,
    metricCapability(bag, metricId),
    nodeLines(bag, metricId, rangeKey, format, gauge)
  );

  const nodes = [
    nodeChart('heap-nodes', '堆使用率', 'JVM 堆使用率', HINT.heap, 'heap', 'heapNodes', 'percent', true, true),
    nodeChart('cpu-nodes', '进程 CPU', '进程 CPU', HINT.cpu, 'cpu', 'cpuNodes', 'percent', true, true),
    nodeChart('disk-nodes', '节点可用磁盘', '节点可用磁盘', HINT.disk, 'disk', 'diskNodes', 'bytes', true, true),
    nodeChart('fd-nodes', '打开文件描述符', '打开文件描述符', HINT.fd, 'fd', 'fdNodes', 'counts', true, true),
    nodeChart('write-nodes', '节点磁盘写入速率', '节点磁盘写入速率', HINT.write, 'write', 'writeNodes', 'byteps', true, false),
    nodeChart('deleted-nodes', '未合并删除文档数', '未合并删除文档数', HINT.deleted, 'deleted', 'deletedNodes', 'counts', true, true)
  ].filter((chart): chart is EsChartModel => chart != null);

  const queue = singleAggChart(
    bag,
    'queues',
    '写入与搜索队列',
    '写入与搜索队列',
    `${HINT.writeQueue}\n${HINT.searchQueue}`,
    'counts',
    true,
    ['writeQueue', 'searchQueue'],
    ['writeQueueAgg', 'searchQueueAgg'],
    ['写入队列', '搜索队列']
  );
  const throughput: EsChartModel[] = [];
  if (queue) throughput.push(queue);
  if (!bag.pending && nodeCount(bag, 'writeQueue') > 3) {
    const chart = nodeChart('write-queue-nodes', '写入队列', '写入队列', HINT.writeQueue, 'writeQueue', 'writeQueueNodes', 'counts', true, true);
    if (chart) throughput.push(chart);
  }
  if (!bag.pending && nodeCount(bag, 'searchQueue') > 3) {
    const chart = nodeChart('search-queue-nodes', '搜索队列', '搜索队列', HINT.searchQueue, 'searchQueue', 'searchQueueNodes', 'counts', true, true);
    if (chart) throughput.push(chart);
  }
  const httpOpenChart = singleAggChart(
    bag,
    'http-open',
    'HTTP 当前连接',
    'HTTP 当前连接',
    HINT.httpOpen,
    'counts',
    true,
    ['httpOpen'],
    ['httpOpenAgg'],
    ['当前连接']
  );
  const httpRateChart = singleAggChart(
    bag,
    'http-rate',
    'HTTP 每秒新建连接',
    'HTTP 每秒新建连接',
    HINT.httpRate,
    'cps',
    true,
    ['httpOpened'],
    ['httpRateAgg'],
    ['每秒新建连接']
  );
  if (httpOpenChart) throughput.push(httpOpenChart);
  if (httpRateChart) throughput.push(httpRateChart);

  const breakers = singleAggChart(
    bag,
    'breakers',
    '熔断触发',
    '熔断触发',
    `${HINT.field}\n${HINT.request}\n${HINT.parent}`,
    'cps',
    true,
    ['breakerField', 'breakerRequest', 'breakerParent'],
    ['breakerField', 'breakerRequest', 'breakerParent'],
    ['Fielddata 熔断', '请求熔断', '父级熔断']
  );
  const gc = nodeChart('gc', '年轻代 GC 每秒耗时', '年轻代 GC 每秒耗时', HINT.gc, 'gc', 'gcNodes', 'msps', true, false);
  const breakerCharts = [breakers, gc].filter((chart): chart is EsChartModel => chart != null);

  const tabs: EsView['tabs'] = [{ id: 'overview', title: '概览' }];
  if (bag.pending || nodes.length > 0) tabs.push({ id: 'nodes', title: '节点与资源' });
  if (bag.pending || throughput.length > 0) tabs.push({ id: 'throughput', title: '吞吐与队列' });
  if (bag.pending || breakerCharts.length > 0) tabs.push({ id: 'breakers', title: '熔断与回收' });

  return {
    pending: bag.pending,
    healthLabel: bag.pending ? '' : healthLabel(healthCode),
    healthTone: bag.pending ? 'unknown' : healthTone(healthCode),
    collectionLabel: bag.pending ? '' : collectionLabel(collection.kind === 'unknown' && !bag.hasInstance ? { kind: 'not-attached' } : collection),
    tabs,
    overview,
    nodes,
    throughput,
    breakers: breakerCharts
  };
};

export const pendingElasticsearchView = (): EsView => assembleElasticsearch(emptyBag({
  pending: true,
  hasInstance: false,
  nowSeconds: 0,
  freshSeconds: freshWindowSeconds(null),
  alertCount: null,
  alertPending: true
}));
