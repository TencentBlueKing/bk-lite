export const useActiveMQConfig = () => {
  return {
    instance_type: 'activemq',
    dashboardDisplay: [],
    groupIds: {},
    collectTypes: {
      'ActiveMQ-JMX': 'jmx',
      ActiveMQ: 'middleware',
    },
  };
};
