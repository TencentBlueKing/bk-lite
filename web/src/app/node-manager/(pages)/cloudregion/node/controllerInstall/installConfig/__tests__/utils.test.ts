import { describe, expect, it } from 'vitest';
import {
  applyIpAsDefaultNodeName,
  applyWinrmCertificateValidation,
  DEFAULT_WINRM_CERTIFICATE_VALIDATION,
  parseControllerVersion,
  pickLatestPackage
} from '../utils';

describe('applyIpAsDefaultNodeName', () => {
  it('uses the IP as the default node name when the name is empty', () => {
    expect(
      applyIpAsDefaultNodeName(
        { key: 'node-1', ip: null, node_name: null },
        '10.0.0.8'
      )
    ).toEqual({ key: 'node-1', ip: '10.0.0.8', node_name: '10.0.0.8' });
  });

  it('keeps the generated node name synchronized when the IP changes', () => {
    expect(
      applyIpAsDefaultNodeName(
        { key: 'node-1', ip: '10.0.0.8', node_name: '10.0.0.8' },
        '10.0.0.9'
      )
    ).toEqual({ key: 'node-1', ip: '10.0.0.9', node_name: '10.0.0.9' });
  });

  it('preserves a user-defined node name when the IP changes', () => {
    expect(
      applyIpAsDefaultNodeName(
        { key: 'node-1', ip: '10.0.0.8', node_name: 'production-node' },
        '10.0.0.9'
      )
    ).toEqual({
      key: 'node-1',
      ip: '10.0.0.9',
      node_name: 'production-node'
    });
  });

  it('clears only an automatically generated node name with the IP', () => {
    const generatedRow = {
      key: 'generated',
      ip: '10.0.0.8',
      node_name: '10.0.0.8'
    };
    const customRow = {
      key: 'custom',
      ip: '10.0.0.8',
      node_name: 'production-node'
    };

    expect(applyIpAsDefaultNodeName(generatedRow, '')).toEqual({
      key: 'generated',
      ip: '',
      node_name: ''
    });
    expect(applyIpAsDefaultNodeName(customRow, '')).toEqual({
      key: 'custom',
      ip: '',
      node_name: 'production-node'
    });
    expect(generatedRow).toEqual({
      key: 'generated',
      ip: '10.0.0.8',
      node_name: '10.0.0.8'
    });
  });
});

describe('applyWinrmCertificateValidation', () => {
  it('defaults new Windows remote operations to certificate validation disabled', () => {
    expect(DEFAULT_WINRM_CERTIFICATE_VALIDATION).toBe(false);
  });

  it('applies the explicit validation choice to every Windows install row', () => {
    const rows = [
      { key: 'node-1', ip: '10.0.0.8', winrm_cert_validation: true },
      { key: 'node-2', ip: '10.0.0.9', winrm_cert_validation: true }
    ];

    const updated = applyWinrmCertificateValidation(rows, false);

    expect(updated).toEqual([
      { key: 'node-1', ip: '10.0.0.8', winrm_cert_validation: false },
      { key: 'node-2', ip: '10.0.0.9', winrm_cert_validation: false }
    ]);
    expect(rows.every((row) => row.winrm_cert_validation)).toBe(true);
  });
});

describe('pickLatestPackage', () => {
  it('parses standard and v-prefixed versions like the backend', () => {
    expect(parseControllerVersion('1.2.3')).toEqual([1, 2, 3]);
    expect(parseControllerVersion('v2.0.0')).toEqual([2, 0, 0]);
    expect(parseControllerVersion('1.4')).toEqual([1, 4, 0]);
    expect(parseControllerVersion('1.2.3-rc1')).toEqual([0, 0, 0]);
  });

  it('selects the highest semver and uses id as a tie-breaker', () => {
    expect(
      pickLatestPackage([
        { id: 1, version: '1.9.0' },
        { id: 3, version: '1.10.0' },
        { id: 2, version: '1.2.8' }
      ])?.id
    ).toBe(3);
    expect(
      pickLatestPackage([
        { id: 8, version: '2.0.0' },
        { id: 11, version: '2.0.0' }
      ])?.id
    ).toBe(11);
  });

  it('returns undefined for an empty list', () => {
    expect(pickLatestPackage([])).toBeUndefined();
  });
});
