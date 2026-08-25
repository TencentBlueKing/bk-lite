import { describe, expect, it } from 'vitest';

import {
  applyWinrmScheme,
  defaultWinrmPort,
  isWinrmSchemePortMismatch,
  syncWinrmPort
} from '../winrm';

describe('WinRM scheme helpers', () => {
  it('defaults ports by scheme', () => {
    expect(defaultWinrmPort('https')).toBe(5986);
    expect(defaultWinrmPort('http')).toBe(5985);
  });

  it('switches conventional ports when the scheme changes', () => {
    expect(syncWinrmPort(5986, 'http')).toBe(5985);
    expect(syncWinrmPort(5985, 'https')).toBe(5986);
    expect(syncWinrmPort(7443, 'http')).toBe(7443);
  });

  it('rejects well-known scheme and port mismatches', () => {
    expect(isWinrmSchemePortMismatch('https', 5985)).toBe(true);
    expect(isWinrmSchemePortMismatch('http', 5986)).toBe(true);
    expect(isWinrmSchemePortMismatch('https', 5986)).toBe(false);
    expect(isWinrmSchemePortMismatch('http', 5985)).toBe(false);
  });

  it('applies HTTP to every row and disables certificate validation', () => {
    const rows = [
      {
        key: 'node-1',
        port: 5986,
        winrm_scheme: 'https',
        winrm_cert_validation: true
      }
    ];

    expect(applyWinrmScheme(rows, 'http')).toEqual([
      {
        key: 'node-1',
        port: 5985,
        winrm_scheme: 'http',
        winrm_cert_validation: false
      }
    ]);
    expect(rows[0].winrm_scheme).toBe('https');
  });
});
