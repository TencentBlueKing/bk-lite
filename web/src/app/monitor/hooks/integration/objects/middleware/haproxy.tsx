export const useHaproxyConfig = () => {
  return {
    instance_type: 'haproxy',
    dashboardDisplay: [],
    groupIds: {},
    collectTypes: {
      Haproxy: 'middleware',
    },
  };
};
