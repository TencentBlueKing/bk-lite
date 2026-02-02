export const useDockerConfig = () => {
  return {
    instance_type: 'docker',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'docker_n_containers_running' },
      { type: 'value', key: 'docker_n_containers' },
      { type: 'value', key: 'docker_n_containers_stopped' },
    ],
    groupIds: {},
    collectTypes: {
      Docker: 'docker',
    },
  };
};
