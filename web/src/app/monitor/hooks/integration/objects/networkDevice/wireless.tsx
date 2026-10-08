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
      'Wireless Alvarion SNMP': 'snmp_alvarion',
      'Wireless Cambium SNMP': 'snmp_cambium',
      'Wireless UHP SNMP': 'snmp_uhp',
      'Wireless Proxim SNMP': 'snmp_proxim',
      'Wireless Kymata SNMP': 'snmp_kymata',
      'Wireless EnGenius SNMP': 'snmp_engenius',
      'Wireless Tait SNMP': 'snmp_tait',
      'Wireless Aerohive SNMP': 'snmp_aerohive',
      'Wireless Grandstream SNMP': 'snmp_grandstream',
      'Wireless Ubiquiti airFiber SNMP': 'snmp_ubiquiti_airfiber',
      'Wireless ASCOM SNMP': 'snmp_ascom',
      'Wireless Zmtel SNMP': 'snmp_zmtel',
      'Wireless Albentia SNMP': 'snmp_albentia',
      'Wireless LigoWave SNMP': 'snmp_ligowave',
      'Wireless HPE MSM SNMP': 'snmp_hpmsm',
      'Wireless Radwin SNMP': 'snmp_radwin',
      'Wireless Mimosa SNMP': 'snmp_mimosa',
      'Wireless Airspan SNMP': 'snmp_airspan',
      'Wireless ACKSYS SNMP': 'snmp_acksys',
      'Wireless Last Mile Gear CTM SNMP': 'snmp_ctm',
      'Wireless ProSoft Technology SNMP': 'snmp_prosoft',
      'Wireless BATS SNMP': 'snmp_bats',
      'Wireless Xirrus SNMP': 'snmp_xirrus',
      'Wireless Meru SNMP': 'snmp_meru',
      'Wireless Huawei AC SNMP': 'snmp_huawei_ac',
      'Wireless H3C SNMP': 'snmp_h3c',
      'Wireless IgniteNet SNMP': 'snmp_ignitenet',
      'Wireless Ruckus SNMP': 'snmp_ruckus_wireless',
      'Wireless Aruba SNMP': 'snmp_aruba_wireless',
      'Wireless Cisco SNMP': 'snmp_cisco_wireless'
    }
  };
};
