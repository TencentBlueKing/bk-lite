export const useActiveMQConfig = () => {
  return {
    instance_type: 'activemq',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'activemq_topics_consumer_count' },
      { type: 'value', key: 'activemq_topics_enqueue_count' },
      { type: 'value', key: 'activemq_topics_size' },
    ],
    groupIds: {},
    collectTypes: {
      'ActiveMQ-JMX': 'jmx',
      ActiveMQ: 'middleware',
    },
  };
};
