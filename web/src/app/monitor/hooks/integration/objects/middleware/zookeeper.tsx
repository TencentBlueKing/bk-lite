export const useZookeeperConfig = () => {
  return {
    instance_type: 'zookeeper',
    dashboardDisplay: [],
    groupIds: {},
    collectTypes: {
      'Zookeeper-Exporter': 'exporter',
      Zookeeper: 'middleware',
    },
  };
};
