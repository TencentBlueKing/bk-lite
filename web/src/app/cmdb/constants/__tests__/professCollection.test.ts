import { describe, expect, it } from 'vitest';
import {
  buildSnmpTopologyParams,
  getCloudFormInitialValues,
  getPlatformApiFormInitialValues,
  getSnmpTopologyFormValues,
  IP_DISCOVERY_FORM_INITIAL_VALUES,
  IP_DISCOVERY_MIN_TIMEOUT_SECONDS,
  recommendedTopologyIntervalMinutes,
  resolveIpDiscoveryFormTimeout,
  SNMP_FORM_INITIAL_VALUES,
  TOPOLOGY_PROTOCOL_OPTIONS,
  validateNetworkConfigCommands,
} from '../professCollection';

const translate = (
  id: string,
  fallback?: string,
  values?: Record<string, string>
) => {
  const table: Record<string, string> = {
    'Collection.networkConfigFileTask.commandsRequired': 'Enter collection commands',
    'Collection.networkConfigFileTask.dangerousCommand':
      'Command contains a high-risk operation: {command}',
  };
  const template = table[id] || fallback || id;
  return template.replace(/\{(\w+)\}/g, (_, key) => values?.[key] ?? `{${key}}`);
};

describe('SNMP topology interval seam', () => {
  it('defaults an IP subnet scan budget to its 30-second minimum', () => {
    expect(IP_DISCOVERY_MIN_TIMEOUT_SECONDS).toBe(30);
    expect(IP_DISCOVERY_FORM_INITIAL_VALUES.timeout).toBe(
      IP_DISCOVERY_MIN_TIMEOUT_SECONDS
    );
  });

  it('does not copy a legacy per-IP timeout onto a new IP task', () => {
    expect(resolveIpDiscoveryFormTimeout(true, 5)).toBe(30);
    expect(resolveIpDiscoveryFormTimeout(true, 300)).toBe(30);
    expect(resolveIpDiscoveryFormTimeout(false, 5)).toBe(5);
    expect(resolveIpDiscoveryFormTimeout(false, 30)).toBe(30);
    expect(resolveIpDiscoveryFormTimeout(false)).toBe(30);
  });

  it('defaults the SNMP collection timeout to 30 seconds', () => {
    expect(SNMP_FORM_INITIAL_VALUES.timeout).toBe(30);
  });

  it('calculates the recommended topology interval', () => {
    expect(recommendedTopologyIntervalMinutes(30)).toBe(150);
  });

  it('fills legacy tasks from the device cycle', () => {
    expect(
      getSnmpTopologyFormValues({ has_network_topo: true }, 20)
    ).toMatchObject({
      hasNetworkTopo: true,
      topologyIntervalMinutes: 100,
      topologyIntervalMode: 'recommended',
    });
  });

  it('preserves an explicit custom mode even at the recommended value', () => {
    expect(
      getSnmpTopologyFormValues(
        {
          topology_interval_minutes: 150,
          topology_interval_mode: 'custom',
        },
        30
      )
    ).toMatchObject({
      topologyIntervalMinutes: 150,
      topologyIntervalMode: 'custom',
    });
  });

  it('maps form values to persisted snake-case params', () => {
    expect(
      buildSnmpTopologyParams({
        hasNetworkTopo: true,
        topologyIntervalMinutes: 120,
        topologyIntervalMode: 'custom',
        topologyTimeout: 600,
      })
    ).toMatchObject({
      has_network_topo: true,
      topology_interval_minutes: 120,
      topology_interval_mode: 'custom',
      topology_timeout: 600,
    });
  });

  it('defaults topology timeout to 600 seconds', () => {
    expect(getSnmpTopologyFormValues({ has_network_topo: true })).toMatchObject({
      topologyTimeout: 600,
    });
  });

  it('shows Huawei NDP and selects it by default', () => {
    expect(TOPOLOGY_PROTOCOL_OPTIONS.map(({ value }) => value)).toEqual([
      'lldp',
      'huawei_ndp',
      'cdp',
      'fdb',
      'arp',
    ]);
    expect(SNMP_FORM_INITIAL_VALUES.topologyProtocols).toEqual([
      'lldp',
      'huawei_ndp',
      'cdp',
      'fdb',
      'arp',
    ]);
  });

  it('uses the collection object task budget for Sangfor cloud forms', () => {
    expect(getCloudFormInitialValues(3000).timeout).toBe(3000);
    expect(getCloudFormInitialValues(undefined).timeout).toBe(600);
    expect(getCloudFormInitialValues(0).timeout).toBe(600);
    expect(getCloudFormInitialValues(86401).timeout).toBe(600);
  });

  it('translates network config command validation messages', () => {
    expect(validateNetworkConfigCommands('', translate)).toBe(
      'Enter collection commands'
    );
    expect(validateNetworkConfigCommands('reload', translate)).toBe(
      'Command contains a high-risk operation: reload'
    );
    expect(validateNetworkConfigCommands('show version', translate)).toBe('');
  });

  it('uses the collection object task budget for platform API forms', () => {
    expect(getPlatformApiFormInitialValues(3000).timeout).toBe(3000);
    expect(getPlatformApiFormInitialValues(undefined).timeout).toBe(300);
    expect(getPlatformApiFormInitialValues(0).timeout).toBe(300);
    expect(getPlatformApiFormInitialValues(86401).timeout).toBe(300);
  });
});
