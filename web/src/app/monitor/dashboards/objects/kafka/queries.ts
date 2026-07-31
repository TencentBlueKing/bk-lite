export const KAFKA_LAG_TOP_N = 10;

export const KAFKA_LAG_TOP_QUERY = `topk(${KAFKA_LAG_TOP_N}, max by (consumergroup, topic, partition) (kafka_consumergroup_lag_gauge{__$labels__} >= 0))`;

const escapeLabelValue = (value: string) => value.replace(/\\/g, '\\\\').replace(/"/g, '\\"');

export interface KafkaLagDimension {
  consumerGroup: string;
  topic: string;
  partition: string;
}

export const buildKafkaTopNExactQuery = (
  metric: string,
  dimensions: KafkaLagDimension[],
  withConsumerGroup: boolean,
) => {
  if (!dimensions.length) return '';
  const selectors = dimensions.map(({ consumerGroup, topic, partition }) => {
    const labels = [
      `topic="${escapeLabelValue(topic)}"`,
      `partition="${escapeLabelValue(partition)}"`,
    ];
    if (withConsumerGroup) labels.unshift(`consumergroup="${escapeLabelValue(consumerGroup)}"`);
    return `${metric}{__$labels__,${labels.join(',')}}`;
  });
  return `max by (consumergroup, topic, partition) (${selectors.join(' or ')})`;
};
