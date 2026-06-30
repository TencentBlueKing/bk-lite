export const useTransmissionConfig = () => {
  return {
    instance_type: 'transmission',
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
          'ifInErrors',
          'ifOutErrors',
          'ifInUcastPkts',
          'ifOutUcastPkts',
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
      'Transmission Ciena SNMP': 'snmp_ciena',
      'Transmission SAF Tehnika SNMP': 'snmp_saftehnika',
      'Transmission Pan Dacom SNMP': 'snmp_pandacom',
      'Transmission Tachyon SNMP': 'snmp_tachyon',
      'Transmission XKL SNMP': 'snmp_xkl',
      'Transmission Siklu SNMP': 'snmp_siklu',
      'Transmission Viavi SNMP': 'snmp_viavi',
      'Transmission Sycamore SNMP': 'snmp_sycamore',
      'Transmission Infinera SNMP': 'snmp_infinera'
    }
  };
};
