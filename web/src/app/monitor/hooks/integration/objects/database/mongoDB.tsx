import { useMongoDBTelegraf } from '../../plugins/database/mongoDBTelegraf';

export const useMongoDBConfig = () => {
  const mongoDB = useMongoDBTelegraf();
  const plugins = {
    MongoDB: mongoDB,
  };

  return {
    instance_type: 'mongodb',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'mongodb_connections_current' },
      { type: 'value', key: 'mongodb_latency_commands' },
      { type: 'value', key: 'mongodb_resident_megabytes' },
    ],
    groupIds: {},
    plugins,
  };
};
