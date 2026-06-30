export const useLoadbalanceConfig = () => {
  return {
    instance_type: 'loadbalance',
    dashboardDisplay: [
      {
        indexId: 'device_cpu_usage',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '24%'
        }
      },
      {
        indexId: 'device_memory_usage',
        displayType: 'single',
        sortIndex: 1,
        displayDimension: [],
        style: {
          height: '200px',
          width: '24%'
        }
      },
      {
        indexId: 'device_total_incoming_traffic',
        displayType: 'single',
        sortIndex: 2,
        displayDimension: [],
        style: {
          height: '200px',
          width: '24%'
        }
      },
      {
        indexId: 'device_total_outgoing_traffic',
        displayType: 'single',
        sortIndex: 3,
        displayDimension: [],
        style: {
          height: '200px',
          width: '24%'
        }
      },
      {
        indexId: 'snmp_uptime',
        displayType: 'lineChart',
        sortIndex: 4,
        displayDimension: [],
        style: {
          height: '200px',
          width: '100%'
        }
      },
      {
        indexId: 'interfaces',
        displayType: 'multipleIndexsTable',
        sortIndex: 5,
        displayDimension: ['ifOperStatus', 'ifHighSpeed', 'ifInErrors', 'ifOutErrors', 'ifInUcastPkts', 'ifOutUcastPkts', 'ifInOctets', 'ifOutOctets'],
        style: {
          height: '400px',
          width: '100%'
        }
      }
    ],
    groupIds: {
      list: ['instance_id'],
      default: ['instance_id']
    },
    collectTypes: {
      'Loadbalance SNMP General': 'snmp',
      'Loadbalance F5 SNMP': 'snmp_f5',
      'Loadbalance Citrix NetScaler SNMP': 'snmp_netscaler',
      'Loadbalance A10 Thunder SNMP': 'snmp_a10',
      'Loadbalance FortiADC SNMP': 'snmp_fortiadc',
      'Loadbalance Kemp LoadMaster SNMP': 'snmp_kemp',
      'Loadbalance Superiority SNMP': 'snmp_superiority',
      'Loadbalance RELIANOID SNMP': 'snmp_relianoid',
      'Loadbalance Radware Alteon SNMP': 'snmp_alteon',
      'Loadbalance Flow NetFlow': 'netflow',
      'Loadbalance Flow sFlow': 'sflow'
    }
  };
};
