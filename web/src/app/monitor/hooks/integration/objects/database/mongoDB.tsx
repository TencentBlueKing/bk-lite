export const useMongoDBConfig = () => {
  return {
    instance_type: 'mongodb',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'mongodb_connections_current' },
      { type: 'value', key: 'mongodb_page_faults_rate' },
      { type: 'value', key: 'mongodb_latency_commands_avg' },
    ],
    groupIds: {},
    collectTypes: {
      'Mongodb-Exporter': 'exporter',
      MongoDB: 'database',
    },
  };
};
