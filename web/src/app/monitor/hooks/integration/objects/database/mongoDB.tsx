export const useMongoDBConfig = () => {
  return {
    instance_type: 'mongodb',
    dashboardDisplay: [],
    groupIds: {},
    collectTypes: {
      'Mongodb-Exporter': 'exporter',
      MongoDB: 'database',
    },
  };
};
