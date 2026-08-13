export const useDockerContainerConfig = () => {
  return {
    instance_type: 'docker',
    dashboardDisplay: [],
    groupIds: {
      list: ['instance_id', 'container_name'],
      default: ['instance_id', 'container_name']
    },
    collectTypes: {
      Docker: 'docker',
    },
  };
};
