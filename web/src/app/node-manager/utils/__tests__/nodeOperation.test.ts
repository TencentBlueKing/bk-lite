import { describe, expect, it } from 'vitest';

import {
  applyControllerUninstallCertificateValidation,
  buildControllerUninstallRequestNode,
  buildControllerUninstallRow
} from '../nodeOperation';

describe('Windows controller uninstall defaults', () => {
  const node = {
    id: 'windows-node',
    key: 'windows-node',
    operating_system: 'windows',
    ip: '10.0.0.8'
  } as const;

  it('disables certificate validation for a new trusted-network uninstall row', () => {
    expect(buildControllerUninstallRow(node as never).winrm_cert_validation).toBe(false);
  });

  it('keeps the disabled choice in the uninstall request', () => {
    const row = buildControllerUninstallRow(node as never);
    expect(buildControllerUninstallRequestNode(row as never).winrm_cert_validation).toBe(false);
  });

  it('applies an explicit certificate choice to the whole Windows uninstall batch', () => {
    const rows = [buildControllerUninstallRow(node as never)];
    expect(
      applyControllerUninstallCertificateValidation(rows as never, true)[0]
        .winrm_cert_validation
    ).toBe(true);
    expect(rows[0].winrm_cert_validation).toBe(false);
  });
});
