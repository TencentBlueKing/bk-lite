export const useNetworkServiceConfig = () => {
  return {
    instance_type: 'network_service',
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
        displayDimension: ['ifOperStatus', 'ifHighSpeed', 'ifHCInOctets', 'ifHCOutOctets'],
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
      'NetworkService IONODES SNMP': 'snmp_ionodes',
      'NetworkService Infoblox SNMP': 'snmp_infoblox',
      'NetworkService COMET WebSensor SNMP': 'snmp_comet',
      'NetworkService Gigamon SNMP': 'snmp_gigamon',
      'NetworkService GenieATM SNMP': 'snmp_genieatm',
      'NetworkService Accedian SNMP': 'snmp_accedian',
      'NetworkService Dahua SNMP': 'snmp_dahua',
      'NetworkService ZDNS SNMP': 'snmp_zdns',
      'NetworkService Jacarta interSeptor Pro SNMP': 'snmp_jacarta',
      'NetworkService BlueCat SNMP': 'snmp_bluecat',
      'NetworkService Raritan PDU SNMP': 'snmp_raritan_pdu',
      'NetworkService Meinberg LANTIME SNMP': 'snmp_meinberg',
      'NetworkService Endace SNMP': 'snmp_endace',
      'NetworkService AKCP sensorProbe SNMP': 'snmp_akcp',
      'NetworkService DEVA Broadcast SNMP': 'snmp_deva',
      'NetworkService Sensatronics SNMP': 'snmp_sensatronics',
      'NetworkService EndRun SNMP': 'snmp_endrun',
      'NetworkService WTI PDU SNMP': 'snmp_wti_pdu',
      'NetworkService Spectracom SNMP': 'snmp_spectracom',
      'NetworkService Procera PacketLogic SNMP': 'snmp_procera',
      'NetworkService Asentria SiteBoss SNMP': 'snmp_asentria',
      'NetworkService ATEN PE eco PDU SNMP': 'snmp_aten',
      'NetworkService Server Technology Sentry3 SNMP': 'snmp_servertech',
      'NetworkService HW group STE SNMP': 'snmp_hwg_ste',
      'NetworkService Enlogic PDU SNMP': 'snmp_enlogic',
      'NetworkService Rittal CMC III SNMP': 'snmp_rittal',
      'NetworkService Gude PDU SNMP': 'snmp_gude',
      'NetworkService PowerDsine PoE SNMP': 'snmp_powerdsine',
      'NetworkService Geist PDU Environmental SNMP': 'snmp_geist',
      'NetworkService Synaccess SynLink SNMP': 'snmp_synaccess',
      'NetworkService Panduit iPDU SNMP': 'snmp_panduit',
      'NetworkService Wiesemann Theis Web-Thermo-Hygrometer SNMP': 'snmp_wut',
      'NetworkService APC UPS PDU Environmental SNMP': 'snmp_apc',
      'NetworkService CyberPower ePDU2 SNMP': 'snmp_cyberpower',
      'NetworkService Eaton UPS PDU Environmental SNMP': 'snmp_eaton',
      'NetworkService Papouch TH2E SNMP': 'snmp_papouch',
      'NetworkService Tripp Lite UPS PDU Environmental SNMP': 'snmp_tripplite',
      'NetworkService HW group Poseidon SNMP': 'snmp_hwg_poseidon',
      'NetworkService Allot SNMP': 'snmp_allot',
      'NetworkService Emerson NetSure SNMP': 'snmp_netsure',
      'NetworkService EfficientIP SNMP': 'snmp_efficientip',
      'NetworkService Alpha Cordex SNMP': 'snmp_alpha_cordex',
      'NetworkService Nomadix SNMP': 'snmp_nomadix',
      'NetworkService Dataprobe iBoot-PDU SNMP': 'snmp_dataprobe',
      'NetworkService Socomec iPDU UPS SNMP': 'snmp_socomec',
      'NetworkService Eltek SNMP': 'snmp_eltek',
      'NetworkService Liebert PDU UPS Environmental SNMP': 'snmp_liebert',
      'NetworkService NTI ENVIROMUX SNMP': 'snmp_nti',
      'NetworkService Hikvision SNMP': 'snmp_hikvision'
    }
  };
};
