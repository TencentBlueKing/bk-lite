import { describe, expect, it } from 'vitest';
import {
  buildSnmpTopologyParams,
  getCloudFormInitialValues,
  getPlatformApiFormInitialValues,
  getSnmpTopologyFormValues,
  recommendedTopologyIntervalMinutes,
  SNMP_FORM_INITIAL_VALUES,
} from '../professCollection';

describe('SNMP topology interval seam', () => {
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

  it('uses the collection object task budget for Sangfor cloud forms', () => {
    expect(getCloudFormInitialValues(3000).timeout).toBe(3000);
    expect(getCloudFormInitialValues(undefined).timeout).toBe(600);
  });

  it('uses the collection object task budget for platform API forms', () => {
    expect(getPlatformApiFormInitialValues(3000).timeout).toBe(3000);
    expect(getPlatformApiFormInitialValues(undefined).timeout).toBe(300);
  });
});
