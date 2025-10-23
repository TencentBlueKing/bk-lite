import { useMinioBkpull } from '../../plugins/middleware/minioBkpull';

export const useMinioBkpullConfig = () => {
  const minioBkpulPlugin = useMinioBkpull();

  const plugins = {
    Minio: minioBkpulPlugin,
  };

  return {
    instance_type: 'minio',
    dashboardDisplay: [],
    tableDiaplay: [],
    groupIds: {},
    plugins,
  };
};
