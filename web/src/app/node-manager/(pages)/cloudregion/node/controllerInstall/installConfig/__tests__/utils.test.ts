import { describe, expect, it } from 'vitest';
import {
  applyWinrmCertificateValidation,
  DEFAULT_WINRM_CERTIFICATE_VALIDATION
} from '../utils';

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
