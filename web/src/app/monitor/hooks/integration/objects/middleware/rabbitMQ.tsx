export const useRabbitMQConfig = () => {
  return {
    instance_type: 'rabbitmq',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'enum', key: 'rabbitmq_node_running' },
      { type: 'value', key: 'rabbitmq_overview_messages_ready' },
      { type: 'enum', key: 'rabbitmq_node_mem_alarm' },
    ],
    groupIds: {},
    collectTypes: {
      RabbitMQ: 'middleware',
      'RabbitMQ-Exporter': 'exporter',
    },
  };
};
