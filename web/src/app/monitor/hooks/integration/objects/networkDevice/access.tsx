export const useAccessConfig = () => {
  return {
    instance_type: 'access',
    dashboardDisplay: [
      {
        indexId: 'device_total_outgoing_traffic',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%'
        }
      },
      {
        indexId: 'snmp_uptime',
        displayType: 'lineChart',
        sortIndex: 1,
        displayDimension: [],
        style: {
          height: '200px',
          width: '40%'
        }
      },
      {
        indexId: 'device_total_incoming_traffic',
        displayType: 'lineChart',
        sortIndex: 2,
        displayDimension: [],
        style: {
          height: '200px',
          width: '40%'
        }
      },
      {
        indexId: 'interfaces',
        displayType: 'multipleIndexsTable',
        sortIndex: 3,
        displayDimension: [
          'ifOperStatus',
          'ifHighSpeed',
          'ifHCInOctets',
          'ifHCOutOctets'
        ],
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
      'Access BDCOM SNMP': 'snmp_bdcom',
      'Access V-SOL SNMP': 'snmp_vsolution',
      'Access ARRIS Cadant SNMP': 'snmp_arris',
      'Access FiberHome OLT SNMP': 'snmp_fiberhome_olt',
      'Access Zhone DZS SNMP': 'snmp_zhone',
      'Access UTStarcom SNMP': 'snmp_utstarcom',
      'Access Raisecom SNMP': 'snmp_raisecom'
    }
  };
};
