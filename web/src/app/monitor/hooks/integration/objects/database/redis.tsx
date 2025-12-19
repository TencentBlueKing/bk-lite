export const useRedisConfig = () => {
  return {
    instance_type: 'redis',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'redis_used_memory' },
      { type: 'value', key: 'redis_instantaneous_ops_per_sec' },
    ],
    groupIds: {},
    collectTypes: {
      Redis: 'database',
    },
  };
};
