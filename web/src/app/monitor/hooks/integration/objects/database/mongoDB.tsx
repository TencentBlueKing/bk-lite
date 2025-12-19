export const useMongoDBConfig = () => {
  return {
    instance_type: 'mongodb',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'mongodb_connections_current' },
      { type: 'value', key: 'mongodb_latency_commands' },
      { type: 'value', key: 'mongodb_resident_megabytes' },
    ],
    groupIds: {},
    collectTypes: {
      'Mongodb-Exporter': 'exporter',
      MongoDB: 'database',
    },
  };
};
