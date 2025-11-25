import { useActiveMQTelegraf } from '../../plugins/middleware/activeMQTelegraf';

export const useActiveMQConfig = () => {
  const activeMQPlugin = useActiveMQTelegraf();

  const plugins = {
    ActiveMQ: activeMQPlugin,
  };

  return {
    instance_type: 'activemq',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'activemq_topic_consumer_count' },
      { type: 'value', key: 'activemq_connections_gauge' },
      { type: 'progress', key: 'activemq_memory_usage_ratio_gauge' },
      { type: 'value', key: 'activemq_topic_queue_size_value' },
      { type: 'value', key: 'activemq_message_total_rate' },
    ],
    groupIds: {},
    plugins,
  };
};
