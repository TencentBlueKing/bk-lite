export const useDockerContainerConfig = () => {
  return {
    instance_type: 'docker',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'enum', key: 'docker_container_status' },
      { type: 'progress', key: 'docker_container_cpu_usage_percent' },
      { type: 'progress', key: 'docker_container_mem_usage_percent' },
    ],
    groupIds: {},
    collectTypes: {
      Docker: 'docker',
    },
  };
};
