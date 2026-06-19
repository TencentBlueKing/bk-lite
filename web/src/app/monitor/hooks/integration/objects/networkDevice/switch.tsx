export const useSwitchConfig = () => {
  return {
    instance_type: 'switch',
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
          width: '49%'
        }
      },
      {
        indexId: 'device_temperature_celsius',
        displayType: 'lineChart',
        sortIndex: 5,
        displayDimension: ['descr'],
        style: {
          height: '200px',
          width: '49%'
        }
      },
      {
        indexId: 'interfaces',
        displayType: 'multipleIndexsTable',
        sortIndex: 6,
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
      },
      {
        indexId: 'device_fan_state',
        displayType: 'lineChart',
        sortIndex: 7,
        displayDimension: ['descr'],
        style: {
          height: '200px',
          width: '49%'
        }
      },
      {
        indexId: 'device_psu_state',
        displayType: 'lineChart',
        sortIndex: 8,
        displayDimension: ['descr'],
        style: {
          height: '200px',
          width: '49%'
        }
      }
    ],
    groupIds: {
      list: ['instance_id'],
      default: ['instance_id']
    },
    collectTypes: {
      'Switch SNMP General': 'snmp',
      'Switch Cisco SNMP': 'snmp_cisco',
      'Switch Huawei SNMP': 'snmp_huawei',
      'Switch Aruba SNMP': 'snmp_aruba',
      'Switch Juniper SNMP': 'snmp_juniper',
      'Switch Extreme SNMP': 'snmp_extreme',
      'Switch Brocade SNMP': 'snmp_brocade',
      'Switch Alcatel-Lucent SNMP': 'snmp_alcatel',
      'Switch MikroTik SNMP': 'snmp_mikrotik',
      'Switch D-Link SNMP': 'snmp_dlink',
      'Switch Netgear SNMP': 'snmp_netgear',
      'Switch TP-Link SNMP': 'snmp_tplink',
      'Switch Zyxel SNMP': 'snmp_zyxel',
      'Switch QTech SNMP': 'snmp_qtech',
      'Switch Dell Force10 SNMP': 'snmp_dellforce',
      'Switch HP ProCurve SNMP': 'snmp_hphpn',
      'Switch Datacom SNMP': 'snmp_datacom',
      'Switch Eltex SNMP': 'snmp_eltex',
      'Switch SNR SNMP': 'snmp_snr',
      'Switch Flow NetFlow': 'netflow',
      'Switch Flow sFlow': 'sflow'
    }
  };
};
