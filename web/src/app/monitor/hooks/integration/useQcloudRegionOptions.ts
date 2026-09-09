import { useCallback, useEffect, useRef, useState } from 'react';
import { Form, FormInstance, message } from 'antd';
import { useTranslation } from '@/utils/i18n';
import useIntegrationApi from '@/app/monitor/api/integration';

const MASKED_PASSWORD_RE = /^\*+$/;

export type CloudRegionProvider = 'qcloud' | 'aliyun';

export function cloudRegionProviderFromPlugin(config?: {
  instance_type?: string;
  config_type?: string | string[];
} | null): CloudRegionProvider | null {
  if (!config) return null;
  const types = new Set<string>();
  if (config.instance_type) types.add(String(config.instance_type).toLowerCase());
  if (Array.isArray(config.config_type)) {
    for (const item of config.config_type) types.add(String(item).toLowerCase());
  } else if (config.config_type) {
    types.add(String(config.config_type).toLowerCase());
  }
  if (types.has('aliyun')) return 'aliyun';
  if (types.has('qcloud')) return 'qcloud';
  return null;
}

export interface RegionOption {
  label: string;
  value: string;
}

function isUsableSecret(value: unknown): value is string {
  if (typeof value !== 'string') return false;
  const trimmed = value.trim();
  if (!trimmed) return false;
  if (MASKED_PASSWORD_RE.test(trimmed)) return false;
  return true;
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
  },
} as const;

/**
 * 云监控接入：密钥齐全后按账号动态拉取可用地域。
 * 腾讯云可多选；阿里云一配置一地域，只保留单选。
 */
export function useCloudRegionOptions(options: {
  enabled: boolean;
  form: FormInstance;
  cloudRegionId?: number | string;
  provider: CloudRegionProvider;
}) {
  const { enabled, form, cloudRegionId, provider } = options;
  const { t } = useTranslation();
  const { listQcloudRegions, listAliyunRegions } = useIntegrationApi();
  const [regionOptions, setRegionOptions] = useState<RegionOption[]>([]);
  const [loadingRegions, setLoadingRegions] = useState(false);
  const requestSeq = useRef(0);
  const lastAutoKey = useRef('');
  const multiple = provider === 'qcloud';
  const copy = COPY[provider];

  const username = Form.useWatch('username', form);
  const password = Form.useWatch('ENV_PASSWORD', form);

  const fetchRegions = useCallback(
    async (opts?: { silent?: boolean }) => {
      if (!enabled) return;
      if (!isUsableSecret(username) || !isUsableSecret(password)) {
        if (!opts?.silent) {
          message.warning(t(copy.needCredentials[0], copy.needCredentials[1]));
        }
        return;
      }

      const seq = ++requestSeq.current;
      setLoadingRegions(true);
      try {
        const listFn = provider === 'aliyun' ? listAliyunRegions : listQcloudRegions;
        const data = await listFn({
          username: username.trim(),
          password: password.trim(),
          cloud_region_id: cloudRegionId,
        });
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
        setRegionOptions([]);
        message.error(error?.message || t(copy.fetchFailed[0], copy.fetchFailed[1]));
      } finally {
        if (seq === requestSeq.current) {
          setLoadingRegions(false);
        }
      }
    },
    [
      cloudRegionId,
      copy.empty,
      copy.fetchFailed,
      copy.fetched,
      copy.needCredentials,
      enabled,
      form,
      listAliyunRegions,
      listQcloudRegions,
      multiple,
      password,
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
    if (!isUsableSecret(username) || !isUsableSecret(password)) {
      const selected = regionSelection(form.getFieldValue('region'));
      if (selected.length > 0) {
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
      return;
    }
    const autoKey = `${provider}::${username.trim()}::${password.trim()}::${cloudRegionId ?? ''}`;
    if (lastAutoKey.current === autoKey) {
      return;
    }
    lastAutoKey.current = autoKey;
    void fetchRegions({ silent: true });
  }, [enabled, username, password, cloudRegionId, fetchRegions, form, provider]);

  return {
    regionOptions,
    loadingRegions,
    refreshRegions: () => fetchRegions({ silent: false }),
  };
}

export function useQcloudRegionOptions(options: {
  enabled: boolean;
  form: FormInstance;
  cloudRegionId?: number | string;
}) {
  return useCloudRegionOptions({ ...options, provider: 'qcloud' });
}
