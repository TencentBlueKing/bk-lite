import { useRedisTelegraf } from '../../plugins/database/redisTelegraf';

export const useRedisConfig = () => {
  const redis = useRedisTelegraf();
  const plugins = {
    Redis: redis,
  };

  return {
    instance_type: 'redis',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'redis_used_memory' },
      { type: 'value', key: 'redis_instantaneous_ops_per_sec' },
    ],
    groupIds: {},
    plugins,
  };
};
