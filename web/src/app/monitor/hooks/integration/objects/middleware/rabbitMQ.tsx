export const useRabbitMQConfig = () => {
  return {
    instance_type: 'rabbitmq',
    dashboardDisplay: [],
    tableDiaplay: [{ type: 'value', key: 'rabbitmq_overview_messages_ready' }],
    groupIds: {},
    collectTypes: {
      RabbitMQ: 'middleware',
      'RabbitMQ-Exporter': 'exporter',
    },
  };
};
