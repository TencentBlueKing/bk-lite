import { useRabbitMQTelegraf } from '../../plugins/middleware/rabbitMQTelegraf';
import { useRabbitMQExporter } from '../../plugins/middleware/rabbitMQExporter';

export const useRabbitMQConfig = () => {
  const rabbitMQPlugin = useRabbitMQTelegraf();
  const rabbitMQExporter = useRabbitMQExporter();

  const plugins = {
    RabbitMQ: rabbitMQPlugin,
    'RabbitMQ-Exporter': rabbitMQExporter,
  };

  return {
    instance_type: 'rabbitmq',
    dashboardDisplay: [],
    tableDiaplay: [{ type: 'value', key: 'rabbitmq_overview_messages_ready' }],
    groupIds: {},
    plugins,
  };
};
