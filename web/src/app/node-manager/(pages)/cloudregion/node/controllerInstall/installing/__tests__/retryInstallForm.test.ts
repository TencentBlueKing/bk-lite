import { describe, expect, it } from 'vitest';

import {
  buildRetryInstallParams,
  getRetryInstallInitialValues,
  validateWindowsRetryPort
} from '../retryInstallForm';

describe('Windows controller retry configuration', () => {
  const node = {
    task_id: 39,
    task_node_id: 101,
    os: 'windows',
    port: 7443,
    username: 'Administrator',
    winrm_scheme: 'https',
    winrm_transport: 'ntlm',
    winrm_cert_validation: false
  } as const;

  it('inherits the persisted WinRM profile instead of resetting it', () => {
    expect(getRetryInstallInitialValues(node)).toMatchObject({
      port: 7443,
      username: 'Administrator',
      auth_type: 'password',
      winrm_scheme: 'https',
      winrm_transport: 'ntlm',
      winrm_cert_validation: false
    });
  });

  it('submits the visible WinRM profile with the retry request', () => {
    expect(
      buildRetryInstallParams(
        node,
        {
          port: 5986,
          username: 'Administrator',
          password: 'replacement',
          auth_type: 'password',
          winrm_scheme: 'https',
          winrm_transport: 'ntlm',
          winrm_cert_validation: false
        },
        ''
      )
    ).toMatchObject({
      task_id: 39,
      task_node_ids: [101],
      port: 5986,
      winrm_scheme: 'https',
      winrm_transport: 'ntlm',
      winrm_cert_validation: false
    });
  });

  it('rejects the conventional WinRM HTTP port in HTTPS-only mode', () => {
    expect(validateWindowsRetryPort(5985)).toBe(false);
    expect(validateWindowsRetryPort(5986)).toBe(true);
    expect(validateWindowsRetryPort(7443)).toBe(true);
  });

  it('uses the private-network certificate default when legacy task data has no value', () => {
    expect(
      getRetryInstallInitialValues({
        ...node,
        winrm_cert_validation: undefined
      }).winrm_cert_validation
    ).toBe(false);
  });
});
