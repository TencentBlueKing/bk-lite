export const useFirewallConfig = () => {
  return {
    instance_type: 'firewall',
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
      'Firewall SNMP General': 'snmp',
      'Firewall Fortinet SNMP': 'snmp_fortinet',
      'Firewall Hillstone SNMP': 'snmp_hillstone',
      'Firewall Sophos XG SNMP': 'snmp_sophos',
      'Firewall Forcepoint SNMP': 'snmp_forcepoint',
      'Firewall ScreenOS SNMP': 'snmp_screenos',
      'Firewall Neteye SNMP': 'snmp_neteye',
      'Firewall Bluedon SNMP': 'snmp_bluedon',
      'Firewall Pulse Secure SNMP': 'snmp_pulsesecure',
      'Firewall DPtech SNMP': 'snmp_dptech',
      'Firewall Westone SNMP': 'snmp_westone',
      'Firewall Amaranten SNMP': 'snmp_amaranten',
      'Firewall Secworld SNMP': 'snmp_secworld',
      'Firewall Check Point SNMP': 'snmp_checkpoint',
      'Firewall Stormshield SNMP': 'snmp_stormshield',
      'Firewall Palo Alto SNMP': 'snmp_paloalto',
      'Firewall SonicWall SNMP': 'snmp_sonicwall',
      'Firewall Sangfor SNMP': 'snmp_sangfor',
      'Firewall Kerio Control SNMP': 'snmp_kerio',
      'Firewall Clavister SNMP': 'snmp_clavister',
      'Firewall Blockbit SNMP': 'snmp_blockbit',
      'Firewall Zorp SNMP': 'snmp_zorp',
      'Firewall WatchGuard SNMP': 'snmp_watchguard',
      'Firewall pfSense SNMP': 'snmp_pfsense',
      'Firewall OPNsense SNMP': 'snmp_opnsense',
      'Firewall Flow NetFlow': 'netflow',
      'Firewall Flow sFlow': 'sflow'
    }
  };
};
