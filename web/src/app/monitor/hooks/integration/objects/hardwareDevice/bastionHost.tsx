export const useBastionHostConfig = () => {
  return {
    instance_type: 'bastion_host',
    dashboardDisplay: [
      {
        indexId: 'interface_ifOutDiscards',
        displayType: 'single',
        sortIndex: 0,
        displayDimension: [],
        style: {
          height: '200px',
          width: '15%',
        },
      },
      {
        indexId: 'interface_ifOperStatus',
        displayType: 'lineChart',
        sortIndex: 1,
        displayDimension: [],
        style: {
          height: '200px',
          width: '40%',
        },
      },
      {
        indexId: 'interface_ifInErrors',
        displayType: 'lineChart',
        sortIndex: 2,
        displayDimension: [],
        style: {
          height: '200px',
          width: '40%',
        },
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
          'ifOutOctets',
        ],
        style: {
          height: '400px',
          width: '100%',
        },
      },
    ],
    tableDiaplay: [
      { type: 'enum', key: 'ipmi_chassis_power_state' },
      { type: 'value', key: 'ipmi_fan_speed_rpm' },
      { type: 'value', key: 'ipmi_temperature_celsius' },
    ],
    groupIds: {},
    collectTypes: {
      'Bastion Host SNMP General': 'snmp',
    },
  };
};
