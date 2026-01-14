export const useDockerConfig = () => {
  return {
    instance_type: 'docker',
    dashboardDisplay: [],
    tableDiaplay: [{ type: 'value', key: 'docker_n_containers_running' }],
    groupIds: {},
    collectTypes: {
      Docker: 'docker',
    },
  };
};
