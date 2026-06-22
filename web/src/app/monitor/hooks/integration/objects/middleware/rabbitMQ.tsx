export const useRabbitMQConfig = () => {
  return {
    instance_type: 'rabbitmq',
    dashboardDisplay: [],
    groupIds: {},
    collectTypes: {
      RabbitMQ: 'middleware',
      'RabbitMQ-Exporter': 'exporter',
    },
  };
};
