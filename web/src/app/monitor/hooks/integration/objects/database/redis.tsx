export const useRedisConfig = () => {
  return {
    instance_type: 'redis',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'redis_mem_fragmentation_ratio' },
      { type: 'value', key: 'redis_clients' },
      { type: 'value', key: 'redis_evicted_keys_rate' }
    ],
    groupIds: {},
    collectTypes: {
      Redis: 'database'
    }
  };
};
