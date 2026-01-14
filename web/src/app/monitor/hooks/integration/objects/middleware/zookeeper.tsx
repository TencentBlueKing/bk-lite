export const useZookeeperConfig = () => {
  return {
    instance_type: 'zookeeper',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'zookeeper_num_alive_connections' },
      { type: 'value', key: 'zookeeper_outstanding_requests' },
      { type: 'value', key: 'zookeeper_avg_latency' },
    ],
    groupIds: {},
    collectTypes: {
      'Zookeeper-Exporter': 'exporter',
      Zookeeper: 'middleware',
    },
  };
};
