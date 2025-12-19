export const useZookeeperConfig = () => {
  return {
    instance_type: 'zookeeper',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'avg_latency' },
      { type: 'value', key: 'outstanding_requests' },
      { type: 'value', key: 'approximate_data_size' },
    ],
    groupIds: {},
    collectTypes: {
      'Zookeeper-Exporter': 'exporter',
      Zookeeper: 'middleware',
    },
  };
};
