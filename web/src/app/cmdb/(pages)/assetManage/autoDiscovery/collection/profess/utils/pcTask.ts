/**
 * PC 发现配置采集表单的纯函数契约。
 *
 * 与 server pc_collect_policy 对齐：
 * - 一个任务一种 OS（windows 固定 WinRM/NTLM，macos 固定 SSH），创建后 OS 不可修改；
 * - Windows 仅接受 5986/HTTPS 或显式 5985/HTTP，HTTP 安全提示由 server 写入；
 * - macOS 凭据必须且只能包含密码或私钥之一；
 * - 掩码秘密（PASSWORD_PLACEHOLDER）绝不下发；编辑切换认证方式时显式清空另一种秘密，
 *   由 server 按 credential_id 合并保留未触碰的秘密。
 */
import { PASSWORD_PLACEHOLDER } from '@/app/cmdb/constants/professCollection';
import { CredentialPoolItem } from '@/app/cmdb/types/autoDiscovery';

export type PCOSType = 'windows' | 'macos';
export type PCCredentialShape = 'winrm' | 'macos_ssh';
export type PCAuthType = 'password' | 'privateKey';

export const PC_OS_TYPES: PCOSType[] = ['windows', 'macos'];

const WINDOWS_DEFAULT_CREDENTIAL: CredentialPoolItem = {
  port: 5986,
  scheme: 'https',
  transport: 'ntlm',
  certValidation: false,
};

const MACOS_DEFAULT_CREDENTIAL: CredentialPoolItem = {
  port: 22,
  authType: 'password',
};

export const getPCCredentialShape = (osType: PCOSType): PCCredentialShape =>
  osType === 'windows' ? 'winrm' : 'macos_ssh';

export const getPCDefaults = (osType: PCOSType) => ({
  osType,
  timeout: 120,
  cleanupStrategy: 'immediately',
  credentialPool: [
    osType === 'windows'
      ? { ...WINDOWS_DEFAULT_CREDENTIAL }
      : { ...MACOS_DEFAULT_CREDENTIAL },
  ],
});

const trimString = (value: any) =>
  typeof value === 'string' ? value.trim() : value;

const isMasked = (value: any) => value === PASSWORD_PLACEHOLDER;

const withCredentialId = (item: CredentialPoolItem) =>
  item.credential_id ? { credential_id: item.credential_id } : {};

const normalizeWindowsCredential = (item: CredentialPoolItem) => {
  const credential: Record<string, any> = {
    ...withCredentialId(item),
    username: trimString(item.username),
    port: Number(item.port) || 5986,
  };
  const password = trimString(item.password);
  if (password && !isMasked(password)) {
    credential.password = password;
  }
  return credential;
};

const normalizeMacosCredential = (item: CredentialPoolItem) => {
  const credential: Record<string, any> = {
    ...withCredentialId(item),
    username: trimString(item.username),
    port: Number(item.port) || 22,
  };
  if (item.authType === 'privateKey') {
    const privateKey = trimString(item.private_key);
    if (privateKey && !isMasked(privateKey)) {
      credential.private_key = privateKey;
    }
    const passphrase = trimString(item.passphrase);
    if (passphrase && !isMasked(passphrase)) {
      credential.passphrase = passphrase;
    }
    // 旧凭据是密码（掩码）时切换为私钥：显式清空旧密码，满足 server XOR 校验
    if (isMasked(item.password)) {
      credential.password = '';
    }
  } else {
    const password = trimString(item.password);
    if (password && !isMasked(password)) {
      credential.password = password;
    }
    // 旧凭据是私钥（掩码）时切换为密码：显式清空旧私钥与密码短语
    if (isMasked(item.private_key)) {
      credential.private_key = '';
      credential.passphrase = '';
    }
  }
  return credential;
};

/**
 * 把 PC 表单值转换为提交负载的 params/credential 部分；
 * 其余公共字段由 formatTaskValues 提供，调用方负责合并。
 */
export const buildPCSubmitPayload = (values: {
  osType: PCOSType;
  credentialPool?: CredentialPoolItem[];
}) => {
  const osType = values.osType;
  const pool = (values.credentialPool || []).filter(
    (item) => item && typeof item === 'object'
  );

  if (osType === 'windows') {
    const first = pool[0] || {};
    return {
      params: {
        os_type: 'windows',
        winrm_scheme: first.scheme || 'https',
        winrm_transport: 'ntlm',
        winrm_cert_validation: Boolean(first.certValidation),
      },
      credential: pool.map(normalizeWindowsCredential),
    };
  }

  return {
    params: { os_type: 'macos' },
    credential: pool.map(normalizeMacosCredential),
  };
};

/**
 * 构建编辑/复制任务的表单回填值。
 * server 详情接口已把秘密字段掩码为 PASSWORD_PLACEHOLDER，编辑原样回填；
 * 复制任务清空所有秘密值，但保留 OS（允许用户重新选择）。
 */
export const buildPCFormValues = (detail: any, isCopy: boolean) => {
  const params = detail?.params || {};
  const osType: PCOSType = params.os_type === 'macos' ? 'macos' : 'windows';
  const rawCredential = detail?.credential;
  const pool = Array.isArray(rawCredential)
    ? rawCredential
    : rawCredential
      ? [rawCredential]
      : [];

  const credentialPool = pool
    .filter((item: any) => item && typeof item === 'object')
    .map((item: any) => ({
      ...item,
      scheme: params.winrm_scheme || 'https',
      transport: 'ntlm',
      certValidation: Boolean(params.winrm_cert_validation),
      authType: item.private_key ? 'privateKey' : 'password',
      password: isCopy ? '' : item.password,
      private_key: isCopy ? '' : item.private_key,
      passphrase: isCopy ? '' : item.passphrase,
    }));

  return {
    osType,
    credentialPool,
    taskName: isCopy ? '' : detail?.name,
    organization: detail?.team || [],
    accessPointId: detail?.access_point?.[0]?.id,
  };
};
