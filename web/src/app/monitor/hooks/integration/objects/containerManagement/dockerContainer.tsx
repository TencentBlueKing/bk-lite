export const useDockerContainerConfig = () => {
  return {
    instance_type: 'docker',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'enum', key: 'docker_container_status' },
      { type: 'value', key: 'docker_container_cpu_usage_percent' },
      { type: 'value', key: 'docker_container_mem_usage_percent' },
    ],
    groupIds: {},
    plugins: {},
  };
};
