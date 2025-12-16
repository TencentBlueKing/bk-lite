import { useActiveMQTelegraf } from '../../plugins/middleware/activeMQTelegraf';

export const useActiveMQConfig = () => {
  const activeMQPlugin = useActiveMQTelegraf();

  const plugins = {
    ActiveMQ: activeMQPlugin,
  };

  return {
    instance_type: 'activemq',
    dashboardDisplay: [],
    tableDiaplay: [{ type: 'value', key: 'activemq_topic_consumer_count' }],
    groupIds: {},
    plugins,
  };
};
