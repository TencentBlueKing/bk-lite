import { describe, expect, it } from 'vitest';
import { withTaskCredentialSource } from '../../hooks/formatTaskValues';
import { buildCloudCredential, validateCloudCredential } from '../cloudCredentialConfig';
import { buildRedfishCredential, restoreRedfishCredential } from '../redfishCredential';
import { buildPCSubmitPayload } from '../../utils/pcTask';

describe('已有凭据表单负载', () => {
  it('只携带引用和动态字段，丢弃旧手填认证字段', () => {
    const result = withTaskCredentialSource(
      { credential_source: 'vault', vault_credential_id: 'crd-1', vault_type_key: 'sql' },
      { credential_id: 'cred-1', user: 'old', password: 'old-secret', port: 3306, database: 'app' },
    );
    expect(result).toEqual({
      credential_id: 'cred-1', credential_source: 'vault', vault_credential_id: 'crd-1',
      vault_type_key: 'sql', port: 3306, database: 'app',
    });
  });

  it('非 SNMP 插件仍保留作为采集参数的 version', () => {
    const raw = { credential_source: 'vault' as const, vault_type_key: 'ssh', vault_credential_id: 'crd-ssh-1', version: '2024' };
    expect(withTaskCredentialSource(raw, { version: '2024', port: 22 })).toEqual({
      credential_source: 'vault', vault_type_key: 'ssh', vault_credential_id: 'crd-ssh-1',
      version: '2024', port: 22,
    });
  });

  it('云平台已有凭据可手填 Region 并保留 Project ID', () => {
    const raw = { credential_source: 'vault' as const, vault_credential_id: 'crd-2', regionId: 'cn-north-1', projectId: 'project-1' };
    expect(validateCloudCredential('hwcloud', raw)).toBeNull();
    const result = withTaskCredentialSource(raw, buildCloudCredential('hwcloud', raw));
    expect(result.regions).toEqual({ resource_id: 'cn-north-1', resource_name: 'cn-north-1' });
    expect(result.project_id).toBe('project-1');
    expect(result.accessSecret).toBeUndefined();
  });

  it('Redfish 编辑回显保留仓库 ID 和 TLS/端口', () => {
    const item = restoreRedfishCredential({ credential_source: 'vault', vault_credential_id: 'crd-3', port: 8443, verify_tls: false }, false);
    expect(buildRedfishCredential(item)).toEqual({
      credential_source: 'vault', vault_credential_id: 'crd-3', vault_type_key: undefined,
      port: 8443, verify_tls: false,
    });
  });

  it('PC Windows 仓库凭据仍保留表单端口和连接方式', () => {
    const result = buildPCSubmitPayload({
      osType: 'windows',
      credentialPool: [{ credential_source: 'vault', vault_credential_id: 'crd-4', port: 5985, scheme: 'http', username: 'old', password: 'old-secret' }],
    });
    expect(result.params.winrm_scheme).toBe('http');
    expect(result.credential[0]).toEqual({ credential_source: 'vault', vault_credential_id: 'crd-4', vault_type_key: undefined, port: 5985, scheme: 'http' });
  });
});

it('网络配置的额外特权密码保留，平台账号密码只保存引用', () => {
  const raw = { credential_source: 'vault' as const, vault_type_key: 'platform_api', vault_credential_id: 'platform-1',
    enable_password: 'extra-secret', transport_protocol: 'telnet', port: 2323 };
  const result = withTaskCredentialSource(raw, { ...raw, username: 'stale', password: 'stale' });
  expect(result.enable_password).toBe('extra-secret');
  expect(result.username).toBeUndefined();
  expect(result.password).toBeUndefined();
});


it('SSH 引用保留网络配置额外的特权密码', () => {
  const raw = { credential_source: 'vault' as const, vault_type_key: 'ssh', vault_credential_id: 'ssh-1',
    enable_password: 'enable-secret', transport_protocol: 'telnet', port: 23 };
  expect(withTaskCredentialSource(raw, raw)).toMatchObject(raw);
});
