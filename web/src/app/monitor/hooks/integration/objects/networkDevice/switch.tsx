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
      'Switch Netonix SNMP': 'snmp_netonix',
      'Switch APRESIA SNMP': 'snmp_apresia',
      'Switch Intelbras SNMP': 'snmp_intelbras',
      'Switch EtherWAN SNMP': 'snmp_etherwan',
      'Switch Sixnet SNMP': 'snmp_sixnet',
      'Switch ALLNET SNMP': 'snmp_allnet',
      'Switch Red Lion SNMP': 'snmp_redlion',
      'Switch Alaxala SNMP': 'snmp_alaxala',
      'Switch Transition Networks SNMP': 'snmp_transition',
      'Switch Waystream SNMP': 'snmp_waystream',
      'Switch TsnTec SNMP': 'snmp_tsntec',
      'Switch Antaira SNMP': 'snmp_antaira',
      'Switch XikeStor SNMP': 'snmp_xikestor',
      'Switch RubyTech SNMP': 'snmp_rubytech',
      'Switch Kyland SNMP': 'snmp_kyland',
      'Switch Lantech SNMP': 'snmp_lantech',
      'Switch WAGO SNMP': 'snmp_wago',
      'Switch Weidmuller SNMP': 'snmp_weidmuller',
      'Switch AsterFusion SNMP': 'snmp_asterfusion',
      'Switch ATOP SNMP': 'snmp_atop',
      'Switch Wi-Tek SNMP': 'snmp_witek',
      'Switch Nexans SNMP': 'snmp_nexans',
      'Switch Pica8 SNMP': 'snmp_pica8',
      'Switch Advantech SNMP': 'snmp_advantech',
      'Switch BDCOM SNMP': 'snmp_bdcom',
      'Switch Nokia SNMP': 'snmp_nokia',
      'Switch Parks SNMP': 'snmp_parks',
      'Switch Ubiquiti SNMP': 'snmp_ubiquiti',
      'Switch Ruijie SNMP': 'snmp_ruijie',
      'Switch ZTE SNMP': 'snmp_zte',
      'Switch Alcatel OmniSwitch SNMP': 'snmp_omniswitch',
      'Switch Yamaha SNMP': 'snmp_yamaha',
      'Switch Arista SNMP': 'snmp_arista',
      'Switch Mellanox SNMP': 'snmp_mellanox',
      'Switch Allied Telesis SNMP': 'snmp_alliedtelesis',
      'Switch Dell OS10 SNMP': 'snmp_dellos10',
      'Switch Lenovo CNOS SNMP': 'snmp_lenovocnos',
      'Switch FortiSwitch SNMP': 'snmp_fortiswitch',
      'Switch FiberHome SNMP': 'snmp_fiberhome',
      'Switch H3C SNMP': 'snmp_h3c',
      'Switch Hirschmann SNMP': 'snmp_hirschmann',
      'Switch Westermo SNMP': 'snmp_westermo',
      'Switch Moxa SNMP': 'snmp_moxa',
      'Switch GarretCom SNMP': 'snmp_garretcom',
      'Switch Enterasys SNMP': 'snmp_enterasys',
      'Switch Cumulus SNMP': 'snmp_cumulus',
      'Switch DCN SNMP': 'snmp_dcn',
      'Switch Edgecore SNMP': 'snmp_edgecore',
      'Switch FS SNMP': 'snmp_fs',
      'Switch Korenix SNMP': 'snmp_korenix',
      'Switch Phoenix Contact SNMP': 'snmp_phoenixcontact',
      'Switch Maipu SNMP': 'snmp_maipu',
      'Switch Microsens SNMP': 'snmp_microsens',
      'Switch PLANET SNMP': 'snmp_planet',
      'Switch Pluribus SNMP': 'snmp_pluribus',
      'Switch RuggedCOM SNMP': 'snmp_ruggedcom',
      'Switch Scalance SNMP': 'snmp_scalance',
      'Switch 3Com SNMP': 'snmp_3com',
      'Switch Flow NetFlow': 'netflow',
      'Switch Flow sFlow': 'sflow'
    }
  };
};
