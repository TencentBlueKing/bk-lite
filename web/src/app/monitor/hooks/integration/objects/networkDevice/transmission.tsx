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
      'Transmission Glassway EDFA SNMP': 'snmp_glassway_edfa',
      'Transmission MRV SNMP': 'snmp_mrv',
      'Transmission Nokia Wavence SNMP': 'snmp_nokia_wavence',
      'Transmission Marconi SNMP': 'snmp_marconi',
      'Transmission Alcoma SNMP': 'snmp_alcoma',
      'Transmission Montclair SNMP': 'snmp_montclair',
      'Transmission PacketLight SNMP': 'snmp_packetlight',
      'Transmission Pan Dacom SNMP': 'snmp_pandacom',
      'Transmission BKTel HFC SNMP': 'snmp_bktel_hfc',
      'Transmission Tachyon SNMP': 'snmp_tachyon',
      'Transmission XKL SNMP': 'snmp_xkl',
      'Transmission Siklu SNMP': 'snmp_siklu',
      'Transmission 4RF Aprisa SNMP': 'snmp_4rf',
      'Transmission PBI SNMP': 'snmp_pbi',
      'Transmission Viavi SNMP': 'snmp_viavi',
      'Transmission Sycamore SNMP': 'snmp_sycamore',
      'Transmission Ecreso SNMP': 'snmp_ecreso',
      'Transmission Redline SNMP': 'snmp_redline',
      'Transmission BTI SNMP': 'snmp_bti',
      'Transmission DragonWave SNMP': 'snmp_dragonwave',
      'Transmission Alpine Optoelectronics SNMP': 'snmp_alpineoe',
      'Transmission Ericsson SNMP': 'snmp_ericsson',
      'Transmission MNI Proteus SNMP': 'snmp_mni_proteus',
      'Transmission Ekinops SNMP': 'snmp_ekinops',
      'Transmission Profline SNMP': 'snmp_profline',
      'Transmission Infinera SNMP': 'snmp_infinera',
      'Transmission BridgeWave SNMP': 'snmp_bridgewave',
      'Transmission FiberRoad SNMP': 'snmp_fiberroad',
      'Transmission Huber+Suhner Cubo SNMP': 'snmp_hubersuhner',
      'Transmission TERRA SNMP': 'snmp_terra',
      'Transmission Fibrolan SNMP': 'snmp_fibrolan',
      'Transmission Exalt SNMP': 'snmp_exalt',
      'Transmission Fibernet XMUX SNMP': 'snmp_fibernet_xmux',
      'Transmission Smartoptics SNMP': 'snmp_smartoptics',
      'Transmission RACOM SNMP': 'snmp_racom',
      'Transmission TBS SNMP': 'snmp_tbs',
      'Transmission SIAE Microelettronica SNMP': 'snmp_siae',
      'Transmission Inovonics SNMP': 'snmp_inovonics',
      'Transmission Ifotec SNMP': 'snmp_ifotec',
      'Transmission ADVA SNMP': 'snmp_adva'
    }
  };
};
