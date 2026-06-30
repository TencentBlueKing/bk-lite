export const useRouterConfig = () => {
  return {
    instance_type: 'router',
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
      'Router SNMP General': 'snmp',
      'Router Juniper MX SNMP': 'snmp_juniper_mx',
      'Router Huawei AR SNMP': 'snmp_huawei_ar',
      'Router Vyatta SNMP': 'snmp_vyatta',
      'Router NetModule SNMP': 'snmp_netmodule',
      'Router MultiTech SNMP': 'snmp_multitech',
      'Router Avici SNMP': 'snmp_avici',
      'Router Unisphere SNMP': 'snmp_unisphere',
      'Router 6WIND VSR SNMP': 'snmp_6wind',
      'Router Sierra Wireless SNMP': 'snmp_sierrawireless',
      'Router NEC SNMP': 'snmp_nec',
      'Router DrayTek SNMP': 'snmp_draytek',
      'Router Adtran SNMP': 'snmp_adtran',
      'Router LANCOM SNMP': 'snmp_lancom',
      'Router Cradlepoint SNMP': 'snmp_cradlepoint',
      'Router Teltonika SNMP': 'snmp_teltonika',
      'Router Digi SNMP': 'snmp_digi',
      'Router Versa SNMP': 'snmp_versa',
      'Router Viprinet SNMP': 'snmp_viprinet',
      'Router OneAccess SNMP': 'snmp_oneaccess',
      'Router Harbour SNMP': 'snmp_harbour',
      'Router Aethra SNMP': 'snmp_aethra',
      'Router VeloCloud SNMP': 'snmp_velocloud',
      'Router Benu SNMP': 'snmp_benu',
      'Router Flow NetFlow': 'netflow',
      'Router Flow sFlow': 'sflow'
    }
  };
};
