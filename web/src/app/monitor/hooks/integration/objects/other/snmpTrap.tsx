import { usePingTelegraf } from '../../plugins/other/snmpTrapTelegraf';

export const useSnmpTrapConfig = () => {
  const plugin = usePingTelegraf();

  // 所有插件配置
  const plugins = {
    'SNMP Trap': plugin,
  };

  return {
    instance_type: 'snmp_trap',
    dashboardDisplay: [],
    tableDiaplay: [],
    groupIds: {},
    plugins,
  };
};
