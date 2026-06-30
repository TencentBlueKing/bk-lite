export const useWirelessConfig = () => {
  return {
    instance_type: 'wireless',
    dashboardDisplay: [
      {
        indexId: 'snmp_uptime',
        displayType: 'lineChart',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '40%'
        }
      },
      {
        indexId: 'device_total_incoming_traffic',
        displayType: 'lineChart',
        sortIndex: 1,
        displayDimension: [],
        style: {
          height: '200px',
          width: '30%'
        }
      },
      {
        indexId: 'device_total_outgoing_traffic',
        displayType: 'lineChart',
        sortIndex: 2,
        displayDimension: [],
        style: {
          height: '200px',
          width: '30%'
        }
      },
      {
        indexId: 'interfaces',
        displayType: 'multipleIndexsTable',
        sortIndex: 3,
        displayDimension: [
          'ifOperStatus',
          'ifHighSpeed',
          'ifInOctets',
          'ifOutOctets'
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
      'Wireless Cambium SNMP': 'snmp_cambium',
      'Wireless Proxim SNMP': 'snmp_proxim',
      'Wireless EnGenius SNMP': 'snmp_engenius',
      'Wireless Aerohive SNMP': 'snmp_aerohive',
      'Wireless Grandstream SNMP': 'snmp_grandstream',
      'Wireless ASCOM SNMP': 'snmp_ascom',
      'Wireless Albentia SNMP': 'snmp_albentia',
      'Wireless LigoWave SNMP': 'snmp_ligowave',
      'Wireless Radwin SNMP': 'snmp_radwin'
    }
  };
};
