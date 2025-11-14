import { useRabbitMQTelegraf } from '../../plugins/middleware/rabbitMQTelegraf';

export const useRabbitMQConfig = () => {
  const rabbitMQPlugin = useRabbitMQTelegraf();

  const plugins = {
    RabbitMQ: rabbitMQPlugin,
  };

  return {
    instance_type: 'rabbitmq',
    dashboardDisplay: [],
    tableDiaplay: [{ type: 'value', key: 'rabbitmq_overview_messages_ready' }],
    groupIds: {},
    plugins,
  };
};
