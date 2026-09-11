import { useCallback, useEffect, useRef, useState, type Dispatch, type SetStateAction } from 'react';
import { Form, FormInstance, message } from 'antd';
import { useTranslation } from '@/utils/i18n';
import useIntegrationApi from '@/app/monitor/api/integration';
import { showRequestErrorToast } from '@/utils/requestErrorToast';

const MASKED_PASSWORD_RE = /^\*+$/;
const STORED_SECRET_RE = /^[A-Za-z0-9_-]{40,}$/;

export type CloudRegionProvider = 'qcloud' | 'aliyun';

export interface CloudRegionProviderHints {
  objectName?: string;
  pluginName?: string;
}

function addCloudProviderTokens(tokens: Set<string>, value: unknown) {
  const text = String(value || '').trim().toLowerCase();
  if (!text) return;
  tokens.add(text);
  for (const part of text.split(/[^a-z0-9]+/)) {
    if (part) tokens.add(part);
  }
}

function isAliyunToken(token: string) {
  return token.includes('aliyun') || token.includes('阿里云');
}

function isQcloudToken(token: string) {
  return (
    token.includes('qcloud') ||
    token.includes('tencent') ||
    token.includes('腾讯云')
  );
}

/**
 * 按监控对象/插件身份选择地域拉取通道。
 * 阿里云对象即使 UI.json 仍残留 qcloud instance_type，也必须走阿里云 DescribeRegions，
 * 否则会把 AccessKey 送到腾讯云 SDK，弹出 TencentCloudSDKException。
 */
export function cloudRegionProviderFromPlugin(
  config?: {
    instance_type?: string;
    config_type?: string | string[];
    object_name?: string;
    name?: string;
  } | null,
  extras?: CloudRegionProviderHints
): CloudRegionProvider | null {
  const tokens = new Set<string>();
  addCloudProviderTokens(tokens, extras?.objectName);
  addCloudProviderTokens(tokens, extras?.pluginName);
  addCloudProviderTokens(tokens, config?.object_name);
  addCloudProviderTokens(tokens, config?.name);
  addCloudProviderTokens(tokens, config?.instance_type);
  if (Array.isArray(config?.config_type)) {
    for (const item of config.config_type) addCloudProviderTokens(tokens, item);
  } else if (config?.config_type) {
    addCloudProviderTokens(tokens, config.config_type);
  }
  const list = [...tokens];
  if (list.some(isAliyunToken)) return 'aliyun';
  if (list.some(isQcloudToken)) return 'qcloud';
  return null;
}

/** 资产编辑行：抽屉传的是 objName，不是 monitor_object_name。 */
export function cloudRegionProviderHintsFromRow(
  row?: Record<string, unknown> | null
): CloudRegionProviderHints {
  if (!row) return {};
  return {
    objectName: String(
      row.objName ||
        row.monitor_object_name ||
        row.object_name ||
        row.name ||
        ''
    ),
    pluginName: String(row.plugin_name || row.collector || ''),
  };
}

export interface RegionOption {
  label: string;
  value: string;
}

export type CloudRegionCredentialSource = 'form' | 'stored';

export interface CloudRegionRequestInput {
  credentialSource?: CloudRegionCredentialSource;
  collectConfigId?: string | number | string[];
  username?: unknown;
  password?: unknown;
  cloudRegionId?: number | string;
  preferFormCredentials?: boolean;
}

export interface CloudRegionRequestPayload {
  collect_config_id?: string;
  collect_config_ids?: string[];
  username?: string;
  password?: string;
  cloud_region_id?: number | string;
}

function isUsableSecret(value: unknown): value is string {
  if (typeof value !== 'string') return false;
  const trimmed = value.trim();
  if (!trimmed) return false;
  if (MASKED_PASSWORD_RE.test(trimmed)) return false;
  return true;
}

function secretText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

/** 编辑回填的 AES 密文通常 ≥40 位 urlsafe base64；腾讯云明文 SecretKey 约 32 位。 */
export function looksLikeStoredCloudSecret(value: unknown): boolean {
  return isUsableSecret(value) && STORED_SECRET_RE.test(value.trim());
}

function withCloudRegionId(
  payload: CloudRegionRequestPayload,
  cloudRegionId?: number | string
): CloudRegionRequestPayload {
  if (cloudRegionId === undefined || cloudRegionId === '') {
    return payload;
  }
  return { ...payload, cloud_region_id: cloudRegionId };
}

function normalizeCollectConfigIds(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map((item) => String(item ?? '').trim()).filter(Boolean);
  }
  const single = String(value ?? '').trim();
  return single ? [single] : [];
}

/**
 * 资产编辑行里取出已存采集配置 ID。优先 child.id，否则用 config_ids。
 */
export function resolveStoredCollectConfigId(row?: {
  config_content?: unknown;
  child?: { id?: unknown };
  config_ids?: unknown[];
  config_id?: unknown;
} | null): string | string[] | undefined {
  const content = row?.config_content as { child?: { id?: unknown } } | undefined;
  const childId = String(content?.child?.id ?? row?.child?.id ?? '').trim();
  if (childId) return childId;
  const ids = (Array.isArray(row?.config_ids) ? row.config_ids : [])
    .map((item) => String(item ?? '').trim())
    .filter(Boolean);
  if (ids.length === 1) return ids[0];
  if (ids.length > 1) return ids;
  const single = String(row?.config_id ?? '').trim();
  return single || undefined;
}

/**
 * 接入页密钥齐全后自动拉地域；资产编辑页打开时只回显已选，避免空密钥打出「均必填」。
 */
export function shouldAutoFetchCloudRegions(
  credentialSource: CloudRegionCredentialSource | undefined,
  request: CloudRegionRequestPayload | null
): boolean {
  if (!request) return false;
  if (credentialSource === 'stored') return false;
  if (looksLikeStoredCloudSecret(request.password)) return false;
  return true;
}

/**
 * 接入页用表单明文密钥拉地域。
 * 资产编辑页默认只传已存配置 ID（回填的 SecretKey 是 AES 密文，不能发给云厂商）。
 * 用户在编辑页改过 SecretKey 后，改走表单明文，避免仍用旧密钥拉地域。
 */
export function buildCloudRegionRequest(
  input: CloudRegionRequestInput
): CloudRegionRequestPayload | null {
  const ids = normalizeCollectConfigIds(input.collectConfigId);
  const formReady = isUsableSecret(input.username) && isUsableSecret(input.password);
  const preferForm =
    Boolean(input.preferFormCredentials) &&
    formReady &&
    !looksLikeStoredCloudSecret(input.password);
  if (preferForm) {
    return withCloudRegionId(
      {
        username: secretText(input.username),
        password: secretText(input.password),
      },
      input.cloudRegionId
    );
  }
  const useStored = input.credentialSource === 'stored' || ids.length > 0;
  if (useStored) {
    if (ids.length) {
      const payload =
        ids.length === 1
          ? { collect_config_id: ids[0] }
          : { collect_config_ids: ids };
      return withCloudRegionId(payload, input.cloudRegionId);
    }
    if (formReady) {
      return withCloudRegionId(
        {
          username: secretText(input.username),
          password: secretText(input.password),
        },
        input.cloudRegionId
      );
    }
    return null;
  }
  if (!formReady) {
    return null;
  }
  return withCloudRegionId(
    {
      username: secretText(input.username),
      password: secretText(input.password),
    },
    input.cloudRegionId
  );
}

function regionSelection(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter(Boolean);
  }
  if (typeof value === 'string' && value.trim()) {
    return value.split(',').map((item) => item.trim()).filter(Boolean);
  }
  return [];
}

const COPY = {
  qcloud: {
    needCredentials: [
      'monitor.integrations.qcloudRegionNeedCredentials',
      '请先填写 SecretId 与 SecretKey，再获取地域',
    ],
    empty: [
      'monitor.integrations.qcloudRegionEmpty',
      '未获取到可用腾讯云地域，请确认密钥权限是否包含 CVM DescribeRegions',
    ],
    fetched: 'monitor.integrations.qcloudRegionFetched',
    fetchFailed: [
      'monitor.integrations.qcloudRegionFetchFailed',
      '获取腾讯云地域失败',
    ],
    needStoredConfig: [
      'monitor.integrations.qcloudRegionNeedStoredConfig',
      '无法读取已存密钥，已保留当前地域',
    ],
  },
  aliyun: {
    needCredentials: [
      'monitor.integrations.aliyunRegionNeedCredentials',
      '请先填写 AccessKey ID 与 AccessKey Secret，再获取地域',
    ],
    empty: [
      'monitor.integrations.aliyunRegionEmpty',
      '未获取到可用阿里云地域，请确认密钥权限是否包含 ECS DescribeRegions',
    ],
    fetched: 'monitor.integrations.aliyunRegionFetched',
    fetchFailed: [
      'monitor.integrations.aliyunRegionFetchFailed',
      '获取阿里云地域失败',
    ],
    needStoredConfig: [
      'monitor.integrations.aliyunRegionNeedStoredConfig',
      '无法读取已存密钥，已保留当前地域',
    ],
  },
} as const;

/**
 * 云监控接入：密钥齐全后按账号动态拉取可用地域。
 * 腾讯云可多选；阿里云一配置一地域，只保留单选。
 */
function seedSelectedRegionOptions(
  form: FormInstance,
  setRegionOptions: Dispatch<SetStateAction<RegionOption[]>>
) {
  const selected = regionSelection(form.getFieldValue('region'));
  if (selected.length === 0) return;
  setRegionOptions((prev) => {
    const existing = new Set(prev.map((item) => item.value));
    const missing = selected.filter((item) => !existing.has(item));
    if (missing.length === 0) {
      return prev;
    }
    return [
      ...prev,
      ...missing.map((item) => ({ label: item, value: item })),
    ];
  });
}

/**
 * 云监控接入：密钥齐全后按账号动态拉取可用地域。
 * 腾讯云可多选；阿里云一配置一地域，只保留单选。
 * 资产编辑页传 credentialSource=stored，用已存配置解密，绝不回填密文。
 */
export function useCloudRegionOptions(options: {
  enabled: boolean;
  form: FormInstance;
  cloudRegionId?: number | string;
  provider: CloudRegionProvider;
  credentialSource?: CloudRegionCredentialSource;
  collectConfigId?: string | number | string[];
}) {
  const {
    enabled,
    form,
    cloudRegionId,
    provider,
    credentialSource = 'form',
    collectConfigId,
  } = options;
  const { t } = useTranslation();
  const { listQcloudRegions, listAliyunRegions } = useIntegrationApi();
  const [regionOptions, setRegionOptions] = useState<RegionOption[]>([]);
  const [loadingRegions, setLoadingRegions] = useState(false);
  const requestSeq = useRef(0);
  const lastAutoKey = useRef('');
  const initialPasswordRef = useRef<string | null>(null);
  const multiple = provider === 'qcloud';
  const copy = COPY[provider];

  const username = Form.useWatch('username', form);
  const password = Form.useWatch('ENV_PASSWORD', form);
  const regionValue = Form.useWatch('region', form);

  useEffect(() => {
    if (!enabled) {
      initialPasswordRef.current = null;
      return;
    }
    if (initialPasswordRef.current === null && isUsableSecret(password)) {
      initialPasswordRef.current = password.trim();
    }
  }, [enabled, password]);

  const preferFormCredentials =
    credentialSource === 'form' ||
    (!looksLikeStoredCloudSecret(password) &&
      isUsableSecret(password) &&
      initialPasswordRef.current !== null &&
      password.trim() !== initialPasswordRef.current);

  const fetchRegions = useCallback(
    async (opts?: { silent?: boolean }) => {
      if (!enabled) return;
      const request = buildCloudRegionRequest({
        credentialSource,
        collectConfigId,
        username,
        password,
        cloudRegionId,
        preferFormCredentials,
      });
      if (!request) {
        seedSelectedRegionOptions(form, setRegionOptions);
        if (!opts?.silent) {
          const missingStored = credentialSource === 'stored';
          message.warning(
            missingStored
              ? t(copy.needStoredConfig[0], copy.needStoredConfig[1])
              : t(copy.needCredentials[0], copy.needCredentials[1])
          );
        }
        return;
      }

      const seq = ++requestSeq.current;
      setLoadingRegions(true);
      try {
        const listFn = provider === 'aliyun' ? listAliyunRegions : listQcloudRegions;
        const data = await listFn(request);
        if (seq !== requestSeq.current) return;
        const next = (Array.isArray(data) ? data : [])
          .map((item: any) => ({
            label: String(item?.label || item?.resource_name || item?.value || item?.resource_id || ''),
            value: String(item?.value || item?.resource_id || ''),
          }))
          .filter((item) => item.value);
        setRegionOptions(next);

        const selected = regionSelection(form.getFieldValue('region'));
        if (selected.length > 0 && next.length > 0) {
          const allowed = new Set(next.map((item) => item.value));
          const kept = selected.filter((item) => allowed.has(item));
          if (multiple) {
            if (kept.length !== selected.length) {
              form.setFieldsValue({ region: kept.length ? kept : undefined });
            }
          } else {
            const nextValue = kept[0];
            const current = form.getFieldValue('region');
            if (nextValue !== current) {
              form.setFieldsValue({ region: nextValue });
            }
          }
        }

        if (next.length === 0) {
          seedSelectedRegionOptions(form, setRegionOptions);
          message.warning(t(copy.empty[0], copy.empty[1]));
          return;
        }
        if (!opts?.silent) {
          message.success(
            t(copy.fetched, '已获取 {count} 个地域', {
              count: next.length,
            })
          );
        }
      } catch (error: any) {
        if (seq !== requestSeq.current) return;
        seedSelectedRegionOptions(form, setRegionOptions);
        if (opts?.silent) return;
        const raw = String(error?.message || '');
        const leakedTencentSdk =
          provider === 'aliyun' &&
          /TencentCloudSDKException|SecretIdNotFound|SecretId不存在/i.test(raw);
        showRequestErrorToast(
          leakedTencentSdk
            ? t(
              'monitor.integrations.aliyunRegionAuthFailed',
              'AccessKey 无效或权限不足，请检查 AccessKey ID / AccessKey Secret'
            )
            : raw || t(copy.fetchFailed[0], copy.fetchFailed[1])
        );
      } finally {
        if (seq === requestSeq.current) {
          setLoadingRegions(false);
        }
      }
    },
    [
      cloudRegionId,
      collectConfigId,
      copy.empty,
      copy.fetchFailed,
      copy.fetched,
      copy.needCredentials,
      copy.needStoredConfig,
      credentialSource,
      enabled,
      form,
      listAliyunRegions,
      listQcloudRegions,
      multiple,
      password,
      preferFormCredentials,
      provider,
      t,
      username,
    ]
  );

  useEffect(() => {
    if (!enabled) {
      setRegionOptions([]);
      lastAutoKey.current = '';
      return;
    }
    const request = buildCloudRegionRequest({
      credentialSource,
      collectConfigId,
      username,
      password,
      cloudRegionId,
      preferFormCredentials,
    });
    if (!request) {
      seedSelectedRegionOptions(form, setRegionOptions);
      return;
    }
    const autoKey = request.collect_config_id
      ? `stored::${provider}::${request.collect_config_id}::${request.cloud_region_id ?? ''}`
      : request.collect_config_ids
        ? `stored::${provider}::${request.collect_config_ids.join(',')}::${request.cloud_region_id ?? ''}`
        : `${provider}::${request.username}::${request.password}::${request.cloud_region_id ?? ''}`;
    if (lastAutoKey.current === autoKey) {
      return;
    }
    if (!shouldAutoFetchCloudRegions(credentialSource, request)) {
      seedSelectedRegionOptions(form, setRegionOptions);
      lastAutoKey.current = autoKey;
      return;
    }
    lastAutoKey.current = autoKey;
    void fetchRegions({ silent: true });
  }, [
    cloudRegionId,
    collectConfigId,
    credentialSource,
    enabled,
    fetchRegions,
    form,
    password,
    preferFormCredentials,
    provider,
    username,
  ]);

  useEffect(() => {
    if (!enabled) return;
    seedSelectedRegionOptions(form, setRegionOptions);
  }, [enabled, form, regionValue]);

  return {
    regionOptions,
    loadingRegions,
    refreshRegions: () => fetchRegions({ silent: false }),
    multiple,
  };
}

export function useQcloudRegionOptions(options: {
  enabled: boolean;
  form: FormInstance;
  cloudRegionId?: number | string;
  credentialSource?: CloudRegionCredentialSource;
  collectConfigId?: string | number | string[];
}) {
  return useCloudRegionOptions({ ...options, provider: 'qcloud' });
}
