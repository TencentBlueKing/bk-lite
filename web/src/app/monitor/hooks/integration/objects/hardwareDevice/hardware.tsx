import { useHardwareSnmpPlugin } from '../../plugins/hardwareDevice/hardwareSnmp';
import { useHardwareIpmiPlugin } from '../../plugins/hardwareDevice/hardwareIpmi';

export const useHardwareConfig = () => {
  const snmpPlugin = useHardwareSnmpPlugin();
  const ipmiPlugin = useHardwareIpmiPlugin();

  // 所有插件配置
  const plugins = {
    'Hardware Server SNMP General': snmpPlugin,
    'Hardware Server IPMI': ipmiPlugin,
  };

  return {
    instance_type: 'hardware_server',
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
