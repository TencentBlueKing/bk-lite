export const useDockerContainerConfig = () => {
  return {
    instance_type: 'docker',
    dashboardDisplay: [],
    groupIds: {},
    collectTypes: {
      Docker: 'docker',
    },
  };
};
