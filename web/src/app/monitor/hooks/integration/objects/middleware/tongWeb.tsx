import { useTongWeb6Jmx } from '../../plugins/middleware/tongWeb6Jmx';
import { useTongWeb7Jmx } from '../../plugins/middleware/tongWeb7Jmx';

export const useTongWebConfig = () => {
  const TongWeb6 = useTongWeb6Jmx();
  const TongWeb7 = useTongWeb7Jmx();

  // 所有插件配置
  const plugins = {
    'TongWeb6-JMX': TongWeb6,
    'TongWeb7-JMX': TongWeb7,
  };

  return {
    instance_type: 'tongweb',
    dashboardDisplay: [],
    tableDiaplay: [],
    groupIds: {},
    plugins,
  };
};
