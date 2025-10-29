import { useStorageSnmpPlugin } from '../../plugins/hardwareDevice/storageSnmp';
import { useStorageIpmiPlugin } from '../../plugins/hardwareDevice/storageIpmi';

export const useStorageConfig = () => {
  const snmpPlugin = useStorageSnmpPlugin();
  const ipmiPlugin = useStorageIpmiPlugin();

  // 所有插件配置
  const plugins = {
    'Storage SNMP General': snmpPlugin,
    'Storage IPMI': ipmiPlugin,
  };

  return {
    instance_type: 'storage',
    dashboardDisplay: [],
    tableDiaplay: [
      { type: 'value', key: 'iftotalInOctets' },
      { type: 'value', key: 'iftotalOutOctets' },
      { type: 'value', key: 'sysUpTime' },
      { type: 'enum', key: 'ipmi_power_watts' },
      { type: 'value', key: 'ipmi_temperature_celsius' },
      { type: 'value', key: 'ipmi_voltage_volts' },
    ],
    groupIds: {},
    plugins,
  };
};
