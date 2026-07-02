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
      'Transmission MRV SNMP': 'snmp_mrv',
      'Transmission Marconi SNMP': 'snmp_marconi',
      'Transmission Alcoma SNMP': 'snmp_alcoma',
      'Transmission PacketLight SNMP': 'snmp_packetlight',
      'Transmission Pan Dacom SNMP': 'snmp_pandacom',
      'Transmission Tachyon SNMP': 'snmp_tachyon',
      'Transmission XKL SNMP': 'snmp_xkl',
      'Transmission Siklu SNMP': 'snmp_siklu',
      'Transmission 4RF Aprisa SNMP': 'snmp_4rf',
      'Transmission Viavi SNMP': 'snmp_viavi',
      'Transmission Sycamore SNMP': 'snmp_sycamore',
      'Transmission Redline SNMP': 'snmp_redline',
      'Transmission DragonWave SNMP': 'snmp_dragonwave',
      'Transmission Ericsson SNMP': 'snmp_ericsson',
      'Transmission Ekinops SNMP': 'snmp_ekinops',
      'Transmission Infinera SNMP': 'snmp_infinera',
      'Transmission BridgeWave SNMP': 'snmp_bridgewave',
      'Transmission Huber+Suhner Cubo SNMP': 'snmp_hubersuhner',
      'Transmission Fibrolan SNMP': 'snmp_fibrolan',
      'Transmission Exalt SNMP': 'snmp_exalt',
      'Transmission Smartoptics SNMP': 'snmp_smartoptics',
      'Transmission RACOM SNMP': 'snmp_racom',
      'Transmission SIAE Microelettronica SNMP': 'snmp_siae'
    }
  };
};
