import { useZookeeperTelegraf } from '../../plugins/middleware/zookeeperTelegraf';
import { useZookeeperExporter } from '../../plugins/middleware/zookeeperExporter';

export const useZookeeperConfig = () => {
  const zookeeperPlugin = useZookeeperTelegraf();
  const zookeeperExporter = useZookeeperExporter();
  const plugins = {
    Zookeeper: zookeeperPlugin,
    'Zookeeper-Exporter': zookeeperExporter,
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
