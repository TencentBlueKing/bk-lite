export const useFirewallConfig = () => {
  return {
    instance_type: 'firewall',
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
      'Firewall SNMP General': 'snmp',
      'Firewall Fortinet SNMP': 'snmp_fortinet',
      'Firewall Hillstone SNMP': 'snmp_hillstone',
      'Firewall Sophos XG SNMP': 'snmp_sophos',
      'Firewall Forcepoint SNMP': 'snmp_forcepoint',
      'Firewall ScreenOS SNMP': 'snmp_screenos',
      'Firewall Check Point SNMP': 'snmp_checkpoint',
      'Firewall Stormshield SNMP': 'snmp_stormshield',
      'Firewall Palo Alto SNMP': 'snmp_paloalto',
      'Firewall SonicWall SNMP': 'snmp_sonicwall',
      'Firewall Sangfor SNMP': 'snmp_sangfor',
      'Firewall Kerio Control SNMP': 'snmp_kerio',
      'Firewall Clavister SNMP': 'snmp_clavister',
      'Firewall WatchGuard SNMP': 'snmp_watchguard',
      'Firewall pfSense SNMP': 'snmp_pfsense',
      'Firewall OPNsense SNMP': 'snmp_opnsense',
      'Firewall Flow NetFlow': 'netflow',
      'Firewall Flow sFlow': 'sflow'
    }
  };
};
