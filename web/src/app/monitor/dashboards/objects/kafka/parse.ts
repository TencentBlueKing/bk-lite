interface RawSeries {
  metric?: Record<string, string>;
  values?: Array<[number, string | number]>;
  value?: [number, string | number];
}

export interface KafkaLagRiskResult {
  [key: string]: { data?: { result?: RawSeries[] } } | null | undefined;
}

export interface KafkaLagRiskRow {
  consumerGroup: string;
  topic: string;
  partition: string;
  lag: number;
  currentOffset: number | null;
  oldestOffset: number | null;
}

const latestValue = (series: RawSeries): number | null => {
  if (series.value) {
    const value = Number(series.value[1]);
    return Number.isFinite(value) ? value : null;
  }
  const values = series.values || [];
  for (let index = values.length - 1; index >= 0; index -= 1) {
    const value = Number(values[index][1]);
    if (Number.isFinite(value)) return value;
  }
  return null;
};

const rowKey = (metric: Record<string, string>) => {
  const consumerGroup = (metric.consumergroup || '').trim();
  const topic = (metric.topic || '').trim();
  const partition = (metric.partition || '').trim();
  return consumerGroup && topic && partition ? [consumerGroup, topic, partition].join('\u0000') : null;
};

const topicPartitionKey = (metric: Record<string, string>) => {
  const topic = (metric.topic || '').trim();
  const partition = (metric.partition || '').trim();
  return topic && partition ? [topic, partition].join('\u0000') : null;
};

const latestByLabel = (raw: KafkaLagRiskResult[string], getKey = rowKey) => {
  const values = new Map<string, number>();
  for (const series of raw?.data?.result || []) {
    const key = getKey(series.metric || {});
    const value = latestValue(series);
    if (key && value != null) values.set(key, value);
  }
  return values;
};

export const buildKafkaLagDimensionKey = (
  consumerGroup: string,
  topic: string,
  partition: string,
) => [consumerGroup, topic, partition].join('\u0000');

export const kafkaLagRowDimensionKey = (row: Pick<KafkaLagRiskRow, 'consumerGroup' | 'topic' | 'partition'>) => (
  buildKafkaLagDimensionKey(row.consumerGroup, row.topic, row.partition)
);

/** 从 renderChart 结果解析 valueN → 消费者组/Topic/分区，用于色序与表格行对齐。 */
export const mapChartSeriesToLagDimensions = (
  history: Array<{ seriesMetrics?: Record<string, Record<string, string>> }>,
): Map<string, string> => {
  const mapping = new Map<string, string>();
  for (const point of history) {
    const seriesMetrics = point.seriesMetrics || {};
    for (const [valueKey, metric] of Object.entries(seriesMetrics)) {
      if (mapping.has(valueKey)) continue;
      const key = rowKey(metric);
      if (key) mapping.set(valueKey, key);
    }
  }
  return mapping;
};

/** 与 EChartsLineChart 一致：含 value 的键按字典序，决定 seriesStyles 下标。 */
export const getSortedChartValueKeys = (
  history: Array<Record<string, unknown>>,
): string[] => {
  const keys = new Set<string>();
  history.forEach((point) => {
    Object.keys(point).forEach((key) => {
      if (key.includes('value')) keys.add(key);
    });
  });
  return Array.from(keys).sort();
};

export const parseKafkaLagRiskRows = (results: KafkaLagRiskResult): KafkaLagRiskRow[] => {
  const lag = latestByLabel(results.lag);
  const currentOffset = latestByLabel(results.currentOffset);
  const oldestOffset = latestByLabel(results.oldestOffset, topicPartitionKey);

  return Array.from(lag.entries())
    .map(([key, lagValue]) => {
      const [consumerGroup, topic, partition] = key.split('\u0000');
      return {
        consumerGroup,
        topic,
        partition,
        lag: lagValue,
        currentOffset: currentOffset.get(key) ?? null,
        oldestOffset: oldestOffset.get([topic, partition].join('\u0000')) ?? null,
      };
    })
    .sort((left, right) => right.lag - left.lag)
    .slice(0, 10);
};
