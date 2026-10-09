'use client';

import React, { useEffect } from 'react';
import { Alert, Form, Radio } from 'antd';
import type { FormInstance } from 'antd';
import { useIntl } from 'react-intl';
import CredentialPicker from '@/components/credential-picker';
import { useTranslation } from '@/utils/i18n';

export interface CredentialVariant {
  key: string;
  when?: { field?: string; value?: unknown };
  type_keys?: string[];
  category?: string;
  anchor_field?: string;
  managed_fields?: string[];
  snmp_version_field?: string | null;
}

const SYNC_ERROR_LABELS: Record<string, [string, string]> = {
  forbidden: ['无权限', 'No access'],
  disabled: ['已停用', 'Disabled'],
  not_found: ['不存在', 'Not found'],
  team_archived: ['组织已归档', 'Organization archived'],
  type_mismatch: ['类型不匹配', 'Type mismatch'],
  incomplete: ['凭据不完整', 'Incomplete credential'],
  version_mismatch: ['版本不匹配', 'Version mismatch'],
  username_invalid: ['用户名无效', 'Invalid username'],
  apply_failed: ['下发失败', 'Apply failed'],
};

export function matchCredentialVariant(
  variants: CredentialVariant[] | undefined,
  values: Record<string, unknown>
): CredentialVariant | null {
  const list = variants || [];
  const matched = list.filter((variant) => whenMatches(variant.when, values));
  if (matched.length === 1) return matched[0];
  if (list.length === 1 && !list[0].when?.field) return list[0];
  return null;
}

function whenMatches(when: CredentialVariant['when'], values: Record<string, unknown>) {
  if (!when?.field) return true;
  const actual = values?.[when.field];
  const expected = when.value;
  if (typeof expected === 'boolean') {
    return asBool(actual) === expected;
  }
  if (typeof expected === 'number') {
    const numeric = Number(actual);
    return Number.isFinite(numeric) ? numeric === expected : String(actual) === String(expected);
  }
  return actual === expected || String(actual ?? '') === String(expected ?? '');
}

function asBool(value: unknown) {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'number') return Boolean(value);
  return ['1', 'true', 'yes', 'on'].includes(String(value || '').trim().toLowerCase());
}

export function syncErrorLabel(code: string, locale: string) {
  const pair = SYNC_ERROR_LABELS[code];
  if (!pair) return code;
  return locale.startsWith('en') ? pair[1] : pair[0];
}

export function CredentialAccessField({
  field,
  variants,
  wasVault,
  renderField,
}: {
  field: any;
  variants: CredentialVariant[];
  wasVault: boolean;
  renderField: (fieldConfig: any) => React.ReactNode;
}) {
  return (
    <Form.Item noStyle shouldUpdate>
      {(form: FormInstance) => {
        const values = form.getFieldsValue(true) as Record<string, unknown>;
        const variant = matchCredentialVariant(variants, values);
        const source = values.credential_source === 'vault' ? 'vault' : 'inline';
        const storedWasVault = Boolean(values.__credential_was_vault) || wasVault;
        const managed = new Set(variant?.managed_fields || []);
        const showSwitch = Boolean(variant && field?.name && field.name === variant.anchor_field);
        const hideManaged = Boolean(
          variant &&
          source === 'vault' &&
          (managed.has(field?.name) || (String(variant.key) === '3' && field?.name === 'sec_level'))
        );
        let nextField = field;
        if (source === 'inline' && storedWasVault && managed.has(field?.name)) {
          nextField = {
            ...field,
            required: true,
            editable: true,
            widget_props: { ...(field?.widget_props || {}), disabled: false },
          };
        }
        return (
          <>
            {showSwitch && variant ? <CredentialSourceSwitch variant={variant} wasVault={storedWasVault} /> : null}
            {hideManaged ? null : renderField(nextField)}
          </>
        );
      }}
    </Form.Item>
  );
}

function CredentialSourceSwitch({
  variant,
  wasVault,
}: {
  variant: CredentialVariant;
  wasVault: boolean;
}) {
  const { t } = useTranslation();
  const intl = useIntl();
  const locale = intl.locale || 'zh';
  const form = Form.useFormInstance();
  const source = Form.useWatch('credential_source', form) || 'inline';
  const credentialId = Form.useWatch('vault_credential_id', form);
  const usable = Form.useWatch('__credential_usable', form);
  const syncError = Form.useWatch('__credential_sync_error', form);
  const syncedAt = Form.useWatch('__credential_synced_at', form);
  const boundName = Form.useWatch('__credential_name', form);
  const boundId = String(Form.useWatch('__credential_bound_id', form) || '');
  const snmpVersion = variant.snmp_version_field ? (Number(variant.key) as 2 | 3) : undefined;

  useEffect(() => {
    if (form.getFieldValue('vault_variant') !== variant.key) {
      form.setFieldValue('vault_variant', variant.key);
    }
  }, [form, variant.key]);

  const keepingOriginal = wasVault && source === 'vault' && boundId !== '' && String(credentialId || '') === boundId;

  return (
    <div className="mb-4 max-w-[720px] space-y-3">
      <Form.Item
        name="credential_source"
        label={t('monitor.integrations.credentialSource', '凭据来源')}
        initialValue="inline"
      >
        <Radio.Group
          onChange={(event) => {
            if (event.target.value === 'inline') {
              form.setFieldValue('credential_source', 'inline');
            }
          }}
        >
          <Radio value="inline">{t('monitor.integrations.credentialManual', '手动填写')}</Radio>
          <Radio value="vault">{t('monitor.integrations.credentialVault', '使用已有凭据')}</Radio>
        </Radio.Group>
      </Form.Item>
      {source === 'vault' ? (
        <>
          {usable === false && keepingOriginal ? (
            <Alert
              type="warning"
              showIcon
              message={t(
                'monitor.integrations.credentialUnusable',
                '当前组织不可使用已绑定的凭据，请另选凭据或改回手填并重新填写'
              )}
            />
          ) : null}
          {syncError && keepingOriginal ? (
            <Alert
              type="error"
              showIcon
              message={t(
                'monitor.integrations.credentialSyncFailed',
                '凭据同步失败：{reason}，请重新选择或检查凭据状态',
                { reason: syncErrorLabel(String(syncError), locale) }
              )}
              description={syncedAt ? String(syncedAt) : undefined}
            />
          ) : null}
          <Form.Item
            name="vault_credential_id"
            label={t('monitor.integrations.credentialPick', '凭据')}
            rules={[{ required: true, message: t('monitor.integrations.credentialRequired', '请选择凭据') }]}
          >
            <CredentialPicker
              category={variant.category}
              types={variant.type_keys}
              snmpVersion={snmpVersion === 2 || snmpVersion === 3 ? snmpVersion : undefined}
              boundOption={
                wasVault && boundId
                  ? {
                    credentialId: boundId,
                    name: String(boundName || boundId),
                    unavailable: usable === false,
                  }
                  : undefined
              }
            />
          </Form.Item>
          <Form.Item name="vault_variant" hidden>
            <input />
          </Form.Item>
        </>
      ) : null}
    </div>
  );
}
