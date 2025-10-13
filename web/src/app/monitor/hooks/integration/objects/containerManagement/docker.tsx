import { useDockerTelegraf } from '../../plugins/containerManagement/dockerTelegraf';

export const useDockerConfig = () => {
  const docker = useDockerTelegraf();
  const plugins = {
    Docker: docker,
  };

  return {
    instance_type: 'docker',
    dashboardDisplay: [],
    tableDiaplay: [{ type: 'value', key: 'docker_n_containers' }],
    groupIds: {},
    plugins,
  };
};
