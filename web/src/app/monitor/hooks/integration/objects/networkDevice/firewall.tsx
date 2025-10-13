import { useFirewallSnmpPlugin } from '../../plugins/networkDevice/firewallSnmp';

export const useFirewallConfig = () => {
  const snmpPlugin = useFirewallSnmpPlugin();

  // 所有插件配置
  const plugins = {
    'Firewall SNMP General': snmpPlugin,
  };

  return {
    instance_type: 'firewall',
    dashboardDisplay: [
      {
        indexId: 'sysUpTime',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'iftotalInOctets',
        displayType: 'lineChart',
        sortIndex: 1,
        displayDimension: [],
        style: {
          height: '200px',
          width: '40%',
        },
      },
      {
        indexId: 'iftotalOutOctets',
        displayType: 'lineChart',
        sortIndex: 2,
        displayDimension: [],
        style: {
          height: '200px',
          width: '40%',
        },
      },
      {
        indexId: 'interfaces',
        displayType: 'multipleIndexsTable',
        sortIndex: 3,
        displayDimension: [
          'ifOperStatus',
          'ifHighSpeed',
          'ifInErrors',
          'ifOutErrors',
          'ifInUcastPkts',
          'ifOutUcastPkts',
          'ifInOctets',
          'ifOutOctets',
        ],
        style: {
          height: '400px',
          width: '100%',
        },
      },
    ],
    tableDiaplay: [
      { type: 'value', key: 'iftotalInOctets' },
      { type: 'value', key: 'iftotalOutOctets' },
      { type: 'value', key: 'sysUpTime' },
    ],
    groupIds: {
      list: ['instance_id'],
      default: ['instance_id'],
    },
    plugins,
  };
};
