export const useDockerContainerConfig = () => {
  return {
    instance_type: 'docker',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'docker_container_status_restart_count' },
      { type: 'progress', key: 'docker_container_cpu_usage_percent' },
    ],
    groupIds: {},
    collectTypes: {
      Docker: 'docker',
    },
  };
};
