/**
 * Hyper-V 配置采集表单的提交与回填。
 *
 * 新建任务默认 HTTP/5985/NTLM，证书校验关闭，与采集器默认值一致。
 * 用户可以改成 HTTPS/5986。WinRM 连接方式写入任务 params，账号、密码和端口写入凭据。
 */
import { PASSWORD_PLACEHOLDER } from '@/app/cmdb/constants/professCollection';
import { CredentialPoolItem } from '@/app/cmdb/types/autoDiscovery';
import { buildCredentialPool } from '../hooks/formatTaskValues';

export const HYPERV_DEFAULT_CREDENTIAL: CredentialPoolItem = {
  port: 5985,
  scheme: 'http',
  transport: 'ntlm',
  certValidation: false,
};

const trimString = (value: unknown): string =>
  typeof value === 'string' ? value.trim() : '';

export const buildHypervSubmitPayload = (values: {
  credentialPool?: CredentialPoolItem[];
}) => {
  const pool = (values.credentialPool || []).filter(
    (item) => item && typeof item === 'object'
  );
  const first = pool[0] || {};
  return {
    params: {
      winrm_scheme: first.scheme || 'http',
      winrm_transport: 'ntlm',
      winrm_cert_validation: Boolean(first.certValidation),
    },
    credential: buildCredentialPool(pool, (item) => {
      const credential: CredentialPoolItem = {
        username: trimString(item.username),
        port: Number(item.port) || 5985,
      };
      const password = trimString(item.password);
      if (password && password !== PASSWORD_PLACEHOLDER) {
        credential.password = password;
      }
      return credential;
    }),
  };
};

export const buildHypervFormValues = (detail: any, isCopy: boolean) => {
  const params = detail?.params || {};
  const rawCredential = detail?.credential;
  const pool = Array.isArray(rawCredential)
    ? rawCredential
    : rawCredential
      ? [rawCredential]
      : [];
  const source = pool.length ? pool : [{ ...HYPERV_DEFAULT_CREDENTIAL }];
  const credentialPool = source
    .filter((item: any) => item && typeof item === 'object')
    .map((item: any) => ({
      ...item,
      port: item.port || 5985,
      scheme: params.winrm_scheme || 'http',
      transport: 'ntlm',
      certValidation: Boolean(params.winrm_cert_validation),
      password:
        item.credential_source === 'vault'
          ? item.password
          : isCopy
            ? ''
            : item.password || PASSWORD_PLACEHOLDER,
    }));

  return {
    credentialPool,
    taskName: isCopy ? '' : detail?.name,
    organization: detail?.team || [],
    accessPointId: detail?.access_point?.[0]?.id,
    ip_precheck: Boolean(params.ip_precheck),
  };
};
