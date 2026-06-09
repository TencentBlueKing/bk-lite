export const useRedisConfig = () => {
  return {
    instance_type: 'redis',
    dashboardDisplay: [],
    groupIds: {},
    collectTypes: {
      Redis: 'database'
    }
  };
};
