import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { PASSWORD_PLACEHOLDER } from '@/app/cmdb/constants/professCollection';
import {
  HYPERV_DEFAULT_CREDENTIAL,
  buildHypervFormValues,
  buildHypervSubmitPayload,
} from '../../utils/hypervTask';

const root = dirname(fileURLToPath(import.meta.url));

describe('hyper-v collection task', () => {
  it('routes hyperv_host to WinRM host selection before the vCenter form', () => {
    const page = readFileSync(resolve(root, '../../page.tsx'), 'utf8');
    const base = readFileSync(resolve(root, '../baseTask.tsx'), 'utf8');
    const editor = readFileSync(resolve(root, '../credentialPoolEditor.tsx'), 'utf8');
    const hyperv = page.indexOf("model_id === 'hyperv_host'");
    const vcenter = page.indexOf("model_id === 'vmware_vc' || taskTypeKey === 'vm'");

    expect(hyperv).toBeGreaterThan(-1);
    expect(vcenter).toBeGreaterThan(hyperv);
    expect(page).toMatch(/HypervTask/);
    expect(page).toMatch(/VMTask/);
    expect(base).toMatch(/modelId === 'hyperv_host'/);
    expect(base).toMatch(/isHypervHostTask/);
    expect(editor).toMatch(/port: 5986/);
    expect(editor).toMatch(/scheme: 'https'/);
  });

  it('keeps the vCenter form on a single vCenter instance', () => {
    const source = readFileSync(resolve(root, '../vmTask.tsx'), 'utf8');
    expect(source).toMatch(/credentialShape="vm"/);
    expect(source).toMatch(/chooseVCenter/);
    expect(source).toMatch(/port: '443'/);
  });

  it('submits IP or host targets with WinRM defaults and keeps the password out of params', () => {
    expect(HYPERV_DEFAULT_CREDENTIAL).toMatchObject({
      port: 5985,
      scheme: 'http',
      transport: 'ntlm',
      certValidation: false,
    });
    const result = buildHypervSubmitPayload({
      credentialPool: [
        {
          ...HYPERV_DEFAULT_CREDENTIAL,
          username: 'administrator',
          password: 'hyperv-secret',
        },
      ],
    });
    expect(result.params).toEqual({
      winrm_scheme: 'http',
      winrm_transport: 'ntlm',
      winrm_cert_validation: false,
    });
    expect(result.credential[0]).toMatchObject({
      username: 'administrator',
      password: 'hyperv-secret',
      port: 5985,
      credential_source: 'inline',
    });
    expect(JSON.stringify(result.params)).not.toContain('hyperv-secret');
  });

  it('preserves an explicit HTTPS port and drops a masked password', () => {
    const result = buildHypervSubmitPayload({
      credentialPool: [
        {
          username: 'ACME\\alice',
          password: PASSWORD_PLACEHOLDER,
          port: 5986,
          scheme: 'https',
          certValidation: true,
        },
      ],
    });
    expect(result.params.winrm_scheme).toBe('https');
    expect(result.params.winrm_cert_validation).toBe(true);
    expect(result.credential[0].port).toBe(5986);
    expect(result.credential[0].password).toBeUndefined();
  });

  it('restores the saved WinRM mode onto the credential editor', () => {
    const values = buildHypervFormValues(
      {
        name: 'hyperv-a',
        team: [1],
        access_point: [{ id: 'node-1' }],
        params: {
          winrm_scheme: 'https',
          winrm_cert_validation: true,
          ip_precheck: true,
        },
        credential: [{ username: 'administrator', password: PASSWORD_PLACEHOLDER, port: 5986 }],
      },
      false,
    );
    expect(values.credentialPool[0]).toMatchObject({
      scheme: 'https',
      port: 5986,
      certValidation: true,
      password: PASSWORD_PLACEHOLDER,
    });
    expect(values.taskName).toBe('hyperv-a');
    expect(values.accessPointId).toBe('node-1');
  });
});
