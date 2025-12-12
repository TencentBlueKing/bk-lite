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
      { type: 'value', key: 'avg_latency' },
      { type: 'value', key: 'outstanding_requests' },
      { type: 'value', key: 'approximate_data_size' },
    ],
    groupIds: {},
    plugins,
  };
};
