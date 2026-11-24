import { formatMetricValue } from '../../../shared/utils/format';
import {
  DOCKER_BLANK,
  collectionStatus,
  containerNames,
  gaugeReading,
  probeCapability,
  samplesForContainer,
  stoppedShare,
  type Capability,
  type CollectionKind,
  type GaugeReading,
  type Probe
} from './reading';
import { batchNow, type InstantSample, type NamedSeries } from './samples';

export interface CountCard {
  kind: 'hidden' | 'blank' | 'value';
  text: string;
}

export interface ShareCard {
  kind: 'hidden' | 'blank' | 'value';
  text: string;
  percent: number | null;
}

export interface DimensionSeries {
  name: string;
  points: NamedSeries['points'];
  reading: string;
}

export interface DimensionChart {
  visible: boolean;
  series: DimensionSeries[];
}

export interface InventoryRow {
  name: string;
  cpu: string;
  memPercent: string;
  memBytes: string;
  restarts: string;
  cpuSort: number | null;
  memSort: number | null;
}

export interface DockerProView {
  collection: CollectionKind;
  running: CountCard;
  stopped: CountCard;
  total: CountCard;
  share: ShareCard;
  containersVisible: boolean;
  cpu: DimensionChart;
  memPercent: DimensionChart;
  memBytes: DimensionChart;
  inventory: InventoryRow[];
}

export interface DockerProInput {
  hasInstance: boolean;
  freshSec: number;
  runningValue: Probe;
  runningTime: Probe;
  runningCapability: Probe;
  stoppedValue: Probe;
  stoppedTime: Probe;
  stoppedCapability: Probe;
  totalValue: Probe;
  totalTime: Probe;
  totalCapability: Probe;
  cpuValue: Probe;
  cpuTime: Probe;
  cpuCapability: Probe;
  cpuChart: readonly NamedSeries[];
  memPercentValue: Probe;
  memPercentTime: Probe;
  memPercentCapability: Probe;
  memPercentChart: readonly NamedSeries[];
  memBytesValue: Probe;
  memBytesTime: Probe;
  memBytesCapability: Probe;
  memBytesChart: readonly NamedSeries[];
  restartValue: Probe;
  restartTime: Probe;
}

const visible = (capability: Capability): boolean => capability !== false;

const countText = (reading: GaugeReading): string => {
  if (reading.kind !== 'fresh') return DOCKER_BLANK;
  const text = Math.abs(reading.value - Math.round(reading.value)) < 1e-6
    ? String(Math.round(reading.value))
    : reading.value.toFixed(1);
  return `${text} 个`;
};

const percentText = (reading: GaugeReading): string => (
  reading.kind === 'fresh' ? formatPercent(reading.value) : DOCKER_BLANK
);

export const formatPercent = (value: number): string => {
  if (!Number.isFinite(value)) return DOCKER_BLANK;
  if (value === 0) return '0%';
  return `${value.toFixed(1)}%`;
};

const bytesText = (reading: GaugeReading): string => {
  if (reading.kind !== 'fresh') return DOCKER_BLANK;
  if (reading.value === 0) return '0 Bytes';
  const formatted = formatMetricValue(reading.value, 'bytes');
  if (formatted.value === '--') return DOCKER_BLANK;
  return formatted.unit ? `${formatted.value} ${formatted.unit}` : formatted.value;
};

const restartText = (reading: GaugeReading): string => {
  if (reading.kind !== 'fresh') return DOCKER_BLANK;
  const text = Math.abs(reading.value - Math.round(reading.value)) < 1e-6
    ? String(Math.round(reading.value))
    : reading.value.toFixed(1);
  return `${text} 次`;
};

const countCard = (capability: Capability, reading: GaugeReading): CountCard => {
  if (!visible(capability)) return { kind: 'hidden', text: '' };
  if (reading.kind !== 'fresh') return { kind: 'blank', text: DOCKER_BLANK };
  return { kind: 'value', text: countText(reading) };
};

const latestPoint = (points: readonly { value: number }[]): number | null => {
  if (!points.length) return null;
  return points[points.length - 1].value;
};

const orderedChart = (series: readonly NamedSeries[]): NamedSeries[] => (
  [...series].sort((left, right) => {
    const leftValue = latestPoint(left.points);
    const rightValue = latestPoint(right.points);
    if (leftValue != null && rightValue != null && leftValue !== rightValue) return rightValue - leftValue;
    if (leftValue == null && rightValue != null) return 1;
    if (leftValue != null && rightValue == null) return -1;
    return left.name.localeCompare(right.name, 'zh');
  })
);

const chartReading = (
  name: string,
  values: Probe,
  times: Probe,
  now: number | null,
  freshSec: number,
  text: (reading: GaugeReading) => string
): string => text(gaugeReading(
  samplesForContainer(values.samples, name),
  samplesForContainer(times.samples, name),
  now,
  freshSec
));

const dimensionChart = (
  capability: Capability,
  series: readonly NamedSeries[],
  readingFor: (name: string) => string
): DimensionChart => {
  if (!visible(capability)) return { visible: false, series: [] };
  return {
    visible: true,
    series: orderedChart(series).map((item) => ({
      name: item.name,
      points: item.points,
      reading: readingFor(item.name)
    }))
  };
};

const sortValue = (reading: GaugeReading): number | null => (
  reading.kind === 'fresh' ? reading.value : null
);

export const buildDockerProView = (input: DockerProInput): DockerProView => {
  const sampleGroups = [
    input.runningValue.samples,
    input.runningTime.samples,
    input.stoppedValue.samples,
    input.stoppedTime.samples,
    input.totalValue.samples,
    input.totalTime.samples,
    input.cpuValue.samples,
    input.cpuTime.samples,
    input.memPercentValue.samples,
    input.memPercentTime.samples,
    input.memBytesValue.samples,
    input.memBytesTime.samples,
    input.restartValue.samples,
    input.restartTime.samples
  ];
  const now = batchNow(sampleGroups);
  const freshSec = input.freshSec;
  const running = gaugeReading(input.runningValue.samples, input.runningTime.samples, now, freshSec);
  const stopped = gaugeReading(input.stoppedValue.samples, input.stoppedTime.samples, now, freshSec);
  const total = gaugeReading(input.totalValue.samples, input.totalTime.samples, now, freshSec);
  const runningCap = probeCapability(input.runningCapability);
  const stoppedCap = probeCapability(input.stoppedCapability);
  const totalCap = probeCapability(input.totalCapability);
  const cpuCap = probeCapability(input.cpuCapability);
  const memPercentCap = probeCapability(input.memPercentCapability);
  const memBytesCap = probeCapability(input.memBytesCapability);
  const share = stoppedShare(total, stopped);
  const shareVisible = totalCap !== false && stoppedCap !== false;
  const names = containerNames([
    input.cpuValue.samples,
    input.memPercentValue.samples,
    input.memBytesValue.samples
  ]);
  const inventory = names.map((name) => {
    const cpu = gaugeReading(
      samplesForContainer(input.cpuValue.samples, name),
      samplesForContainer(input.cpuTime.samples, name),
      now,
      freshSec
    );
    const memPercent = gaugeReading(
      samplesForContainer(input.memPercentValue.samples, name),
      samplesForContainer(input.memPercentTime.samples, name),
      now,
      freshSec
    );
    const memBytes = gaugeReading(
      samplesForContainer(input.memBytesValue.samples, name),
      samplesForContainer(input.memBytesTime.samples, name),
      now,
      freshSec
    );
    const restarts = gaugeReading(
      samplesForContainer(input.restartValue.samples, name),
      samplesForContainer(input.restartTime.samples, name),
      now,
      freshSec
    );
    return {
      name,
      cpu: percentText(cpu),
      memPercent: percentText(memPercent),
      memBytes: bytesText(memBytes),
      restarts: restartText(restarts),
      cpuSort: sortValue(cpu),
      memSort: sortValue(memPercent)
    };
  }).sort((left, right) => {
    const leftCpu = left.cpuSort ?? Number.NEGATIVE_INFINITY;
    const rightCpu = right.cpuSort ?? Number.NEGATIVE_INFINITY;
    if (leftCpu !== rightCpu) return rightCpu - leftCpu;
    const leftMem = left.memSort ?? Number.NEGATIVE_INFINITY;
    const rightMem = right.memSort ?? Number.NEGATIVE_INFINITY;
    if (leftMem !== rightMem) return rightMem - leftMem;
    return left.name.localeCompare(right.name, 'zh');
  });

  return {
    collection: collectionStatus({
      hasInstance: input.hasInstance,
      successTimes: input.totalTime.kind === 'ok' ? input.totalTime.samples.map((sample) => sample.sample) : [],
      failTimes: [],
      now,
      freshSec
    }),
    running: countCard(runningCap, running),
    stopped: countCard(stoppedCap, stopped),
    total: countCard(totalCap, total),
    share: !shareVisible
      ? { kind: 'hidden', text: '', percent: null }
      : share.kind === 'ratio'
        ? { kind: 'value', text: formatPercent(share.percent), percent: share.percent }
        : { kind: 'blank', text: DOCKER_BLANK, percent: null },
    containersVisible: cpuCap !== false || memPercentCap !== false || memBytesCap !== false,
    cpu: dimensionChart(cpuCap, input.cpuChart, (name) => chartReading(
      name, input.cpuValue, input.cpuTime, now, freshSec, percentText
    )),
    memPercent: dimensionChart(memPercentCap, input.memPercentChart, (name) => chartReading(
      name, input.memPercentValue, input.memPercentTime, now, freshSec, percentText
    )),
    memBytes: dimensionChart(memBytesCap, input.memBytesChart, (name) => chartReading(
      name, input.memBytesValue, input.memBytesTime, now, freshSec, bytesText
    )),
    inventory
  };
};

export const emptyProbe = (): Probe => ({ kind: 'ok', samples: [] });

export const okProbe = (samples: readonly InstantSample[]): Probe => ({ kind: 'ok', samples });
