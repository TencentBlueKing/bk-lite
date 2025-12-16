import { useZookeeperTelegraf } from '../../plugins/middleware/zookeeperTelegraf';

export const useZookeeperConfig = () => {
  const zookeeperPlugin = useZookeeperTelegraf();
  const plugins = {
    Zookeeper: zookeeperPlugin,
  };

  return {
    instance_type: 'zookeeper',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'zookeeper_uptime' },
      { type: 'value', key: 'zookeeper_avg_latency' },
    ],
    groupIds: {},
    plugins,
  };
};
