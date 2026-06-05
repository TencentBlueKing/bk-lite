export const useDockerConfig = () => {
  return {
    instance_type: 'docker',
    dashboardDisplay: [],
    groupIds: {},
    collectTypes: {
      Docker: 'docker',
    },
  };
};
