import { useMongoDBTelegraf } from '../../plugins/database/mongoDBTelegraf';
import { useMongoDBExporter } from '../../plugins/database/mongoDBExporter';

export const useMongoDBConfig = () => {
  const mongoDB = useMongoDBTelegraf();
  const mongoDBExporter = useMongoDBExporter();
  const plugins = {
    MongoDB: mongoDB,
    'MongoDB-Exporter': mongoDBExporter,
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
