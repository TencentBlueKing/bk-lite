export const useActiveMQConfig = () => {
  return {
    instance_type: 'activemq',
    dashboardDisplay: [],
    tableDiaplay: [{ type: 'value', key: 'activemq_topic_consumer_count' }],
    groupIds: {},
    collectTypes: {
      'ActiveMQ-JMX': 'jmx',
      ActiveMQ: 'middleware',
    },
  };
};
