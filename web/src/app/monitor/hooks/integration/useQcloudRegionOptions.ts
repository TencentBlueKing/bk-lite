import { useCallback, useEffect, useRef, useState } from 'react';
import { Form, FormInstance, message } from 'antd';
import { useTranslation } from '@/utils/i18n';
import useIntegrationApi from '@/app/monitor/api/integration';

const MASKED_PASSWORD_RE = /^\*+$/;

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

/**
 * 腾讯云监控接入：密钥齐全后按账号动态拉取可用地域。
 */
export function useQcloudRegionOptions(options: {
  enabled: boolean;
  form: FormInstance;
  cloudRegionId?: number | string;
}) {
  const { enabled, form, cloudRegionId } = options;
  const { t } = useTranslation();
  const { listQcloudRegions } = useIntegrationApi();
  const [regionOptions, setRegionOptions] = useState<RegionOption[]>([]);
  const [loadingRegions, setLoadingRegions] = useState(false);
  const requestSeq = useRef(0);
  const lastAutoKey = useRef('');

  const username = Form.useWatch('username', form);
  const password = Form.useWatch('ENV_PASSWORD', form);

  const fetchRegions = useCallback(
    async (opts?: { silent?: boolean }) => {
      if (!enabled) return;
      if (!isUsableSecret(username) || !isUsableSecret(password)) {
        if (!opts?.silent) {
          message.warning(
            t(
              'monitor.integrations.qcloudRegionNeedCredentials',
              '请先填写 SecretId 与 SecretKey，再获取地域'
            )
          );
        }
        return;
      }

      const seq = ++requestSeq.current;
      setLoadingRegions(true);
      try {
        const data = await listQcloudRegions({
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
          if (kept.length !== selected.length) {
            form.setFieldsValue({ region: kept.length ? kept : undefined });
          }
        }

        if (next.length === 0) {
          message.warning(
            t(
              'monitor.integrations.qcloudRegionEmpty',
              '未获取到可用腾讯云地域，请确认密钥权限是否包含 CVM DescribeRegions'
            )
          );
          return;
        }
        if (!opts?.silent) {
          message.success(
            t('monitor.integrations.qcloudRegionFetched', '已获取 {count} 个地域', {
              count: next.length,
            })
          );
        }
      } catch (error: any) {
        if (seq !== requestSeq.current) return;
        setRegionOptions([]);
        // 自动拉取失败也要提示，避免「填了密钥却无回应」。
        message.error(
          error?.message ||
            t('monitor.integrations.qcloudRegionFetchFailed', '获取腾讯云地域失败')
        );
      } finally {
        if (seq === requestSeq.current) {
          setLoadingRegions(false);
        }
      }
    },
    [cloudRegionId, enabled, form, listQcloudRegions, password, t, username]
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
    const autoKey = `${username.trim()}::${password.trim()}::${cloudRegionId ?? ''}`;
    if (lastAutoKey.current === autoKey) {
      return;
    }
    lastAutoKey.current = autoKey;
    void fetchRegions({ silent: true });
  }, [enabled, username, password, cloudRegionId, fetchRegions, form]);

  return {
    regionOptions,
    loadingRegions,
    refreshRegions: () => fetchRegions({ silent: false }),
  };
}
