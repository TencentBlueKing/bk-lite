import { useApacheTelegraf } from '../../plugins/middleware/apacheTelegraf';
import { useApacheExporter } from '../../plugins/middleware/apacheExporter';

export const useApacheConfig = () => {
  const apacheTelegraf = useApacheTelegraf();
  const apacheExporter = useApacheExporter();

  const plugins = {
    Apache: apacheTelegraf,
    'Apache-Exporter': apacheExporter,
  };

  return {
    instance_type: 'apache',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'apache_uptime' },
      { type: 'value', key: 'apache_req_per_sec' },
      { type: 'progress', key: 'apache_cpu_load' },
      { type: 'enum', key: 'apache_up' },
      { type: 'value', key: 'apache_duration_ms_total' },
    ],
    groupIds: {},
    plugins,
  };
};
