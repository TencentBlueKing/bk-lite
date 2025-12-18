export const useDockerConfig = () => {
  return {
    instance_type: 'docker',
    dashboardDisplay: [],
    tableDiaplay: [{ type: 'value', key: 'docker_n_containers' }],
    groupIds: {},
    collectTypes: {
      Docker: 'docker',
    },
  };
};
