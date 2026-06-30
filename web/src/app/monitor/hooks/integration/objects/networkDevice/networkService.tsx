export const useNetworkServiceConfig = () => {
  return {
    instance_type: 'network_service',
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
      'NetworkService Infoblox SNMP': 'snmp_infoblox',
      'NetworkService Gigamon SNMP': 'snmp_gigamon',
      'NetworkService Accedian SNMP': 'snmp_accedian',
      'NetworkService ZDNS SNMP': 'snmp_zdns',
      'NetworkService BlueCat SNMP': 'snmp_bluecat',
      'NetworkService Meinberg LANTIME SNMP': 'snmp_meinberg',
      'NetworkService Endace SNMP': 'snmp_endace',
      'NetworkService DEVA Broadcast SNMP': 'snmp_deva',
      'NetworkService EndRun SNMP': 'snmp_endrun',
      'NetworkService Spectracom SNMP': 'snmp_spectracom',
      'NetworkService Asentria SiteBoss SNMP': 'snmp_asentria',
      'NetworkService Server Technology Sentry3 SNMP': 'snmp_servertech',
      'NetworkService Enlogic PDU SNMP': 'snmp_enlogic',
      'NetworkService Rittal CMC III SNMP': 'snmp_rittal',
      'NetworkService Gude PDU SNMP': 'snmp_gude',
      'NetworkService Geist PDU Environmental SNMP': 'snmp_geist',
      'NetworkService Panduit iPDU SNMP': 'snmp_panduit',
      'NetworkService APC UPS PDU Environmental SNMP': 'snmp_apc',
      'NetworkService Socomec iPDU UPS SNMP': 'snmp_socomec',
      'NetworkService Liebert PDU UPS Environmental SNMP': 'snmp_liebert',
      'NetworkService NTI ENVIROMUX SNMP': 'snmp_nti'
    }
  };
};
