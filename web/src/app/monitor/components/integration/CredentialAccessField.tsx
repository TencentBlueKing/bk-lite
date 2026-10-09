'use client';

import React, { useEffect } from 'react';
import { Alert, Form } from 'antd';
import { KeyOutlined } from '@ant-design/icons';
import type { FormInstance } from 'antd';
import { useIntl } from 'react-intl';
import CredentialPicker from '@/components/credential-picker';
import type { CredentialPickerProps } from '@/components/credential-picker';
import FieldGuideTip from '@/components/field-guide-tip';
import { FORM_WIDGET_WIDTH } from '@/app/monitor/hooks/integration/useConfigRenderer';
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

export function formatCredentialError(message: string, locale: string) {
  const text = String(message || '');
  const matched = text.match(/credential_([a-z0-9_]+)/);
  if (!matched) return text;
  const label = syncErrorLabel(matched[1], locale);
  if (label === matched[1]) return text;
  return label;
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
  const credentialId = Form.useWatch('vault_credential_id', { form, preserve: true });
  // __credential_* 只存在于表单 store，没有对应的 Form.Item，需要 preserve 才能读到。
  const usable = Form.useWatch('__credential_usable', { form, preserve: true });
  const syncError = Form.useWatch('__credential_sync_error', { form, preserve: true });
  const syncedAt = Form.useWatch('__credential_synced_at', { form, preserve: true });
  const boundName = Form.useWatch('__credential_name', { form, preserve: true });
  const boundId = String(Form.useWatch('__credential_bound_id', { form, preserve: true }) || '');
  const snmpVersion = variant.snmp_version_field ? (Number(variant.key) as 2 | 3) : undefined;

  useEffect(() => {
    if (form.getFieldValue('vault_variant') !== variant.key) {
      form.setFieldValue('vault_variant', variant.key);
    }
  }, [form, variant.key]);

  const keepingOriginal = wasVault && source === 'vault' && boundId !== '' && String(credentialId || '') === boundId;
  const requiredMessage = t('monitor.integrations.credentialRequired', '请选择凭据');

  return (
    <div className="max-w-[720px]">
      {/* 「凭据」下拉合一：第一项手动填写（credential_source=inline），其余为已有凭据（vault） */}
      <Form.Item
        name="credential_source"
        initialValue="inline"
        label={
          // 与 useConfigRenderer 的 renderLabel 同一写法：label 内联 FieldGuideTip 灰色问号
          <span className="inline-flex items-center">
            {t('monitor.integrations.credentialPick', '凭据')}
            <FieldGuideTip
              short={t('monitor.integrations.credentialTip')}
              title={t('monitor.integrations.fieldGuideTip')}
            />
          </span>
        }
        extra={
          source === 'vault' ? (
            <span className="text-[12px] leading-[18px] text-[var(--color-text-3)]">
              {t('monitor.integrations.credentialVaultManagedHint', '密码由凭据库管理')}
            </span>
          ) : undefined
        }
        required
        rules={[
          {
            validator: (_, value) =>
              value === 'vault' && !form.getFieldValue('vault_credential_id')
                ? Promise.reject(new Error(requiredMessage))
                : Promise.resolve(),
          },
        ]}
      >
        <CredentialSourceSelect
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
      {source === 'vault' ? (
        <>
          {(usable === false || syncError) && keepingOriginal ? (
            <div className="mb-6 space-y-3">
              {usable === false ? (
                <Alert
                  type="warning"
                  showIcon
                  message={t(
                    'monitor.integrations.credentialUnusable',
                    '当前组织不可使用已绑定的凭据，请另选凭据或改回手填并重新填写'
                  )}
                />
              ) : null}
              {syncError ? (
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
            </div>
          ) : null}
          <Form.Item name="vault_credential_id" hidden>
            <input />
          </Form.Item>
          <Form.Item name="vault_variant" hidden>
            <input />
          </Form.Item>
        </>
      ) : null}
    </div>
  );
}

const MANUAL_OPTION_VALUE = '__credential_manual__';

// 只作用于「凭据」这一个下拉：浅主题色底 + 主题色浅边框，hover/聚焦用主题色；
// 校验失败（status-error）时不覆盖边框，保留 antd 的红框。颜色均为主题变量，暗色模式自动跟随。
const CREDENTIAL_SELECT_CLASS = [
  '[&_.ant-select-selector]:!bg-[var(--color-primary-bg-active)]',
  '[&:not(.ant-select-status-error)_.ant-select-selector]:!border-[color:color-mix(in_srgb,var(--color-primary)_45%,transparent)]',
  '[&:not(.ant-select-status-error):not(.ant-select-disabled):hover_.ant-select-selector]:!border-[color:var(--color-primary)]',
  '[&.ant-select-focused:not(.ant-select-status-error)_.ant-select-selector]:!border-[color:var(--color-primary)]',
].join(' ');

/**
 * 作为 `credential_source` 的受控子组件：
 * - 选「手动填写」→ onChange('inline')
 * - 选某条凭据 → 先写入 vault_credential_id，再 onChange('vault')
 * onChange 走 Form.Item 的受控通道，每次选择都会触发表单 onValuesChange。
 */
function CredentialSourceSelect({
  value,
  onChange,
  ...pickerProps
}: Pick<CredentialPickerProps, 'category' | 'types' | 'snmpVersion' | 'boundOption'> & {
  value?: string;
  onChange?: (value: string) => void;
}) {
  const { t } = useTranslation();
  const form = Form.useFormInstance();
  const credentialId = Form.useWatch('vault_credential_id', { form, preserve: true });
  const manualLabel = t('monitor.integrations.credentialManual', '手动填写');
  const selected = value === 'vault'
    ? (credentialId ? String(credentialId) : undefined)
    : MANUAL_OPTION_VALUE;

  return (
    <CredentialPicker
      {...pickerProps}
      value={selected}
      manualOption={{
        value: MANUAL_OPTION_VALUE,
        label: manualLabel,
        searchText: manualLabel,
        groupLabel: t('monitor.integrations.credentialSaved', '已有凭据'),
        emptyText: t('monitor.integrations.credentialEmpty', '暂无凭据'),
        prefix: <KeyOutlined className="text-[var(--color-primary)]" />,
        selectClassName: CREDENTIAL_SELECT_CLASS,
        selectStyle: { width: FORM_WIDGET_WIDTH },
      }}
      onChange={(next) => {
        if (!next || next === MANUAL_OPTION_VALUE) {
          onChange?.('inline');
          return;
        }
        form.setFieldValue('vault_credential_id', next);
        onChange?.('vault');
      }}
    />
  );
}
