'use client';

import React from 'react';
import { Form, Input, Select } from 'antd';
import type { FormInstance } from 'antd/es/form';
import { useTranslation } from '@/utils/i18n';
import { CREDENTIAL_CATEGORIES, CREDENTIAL_CATEGORY_ZH_LABELS } from './types';
import type { CredentialGroupOption, CredentialTypeItem } from './types';
import { CredentialFieldsBlock } from './fields';

export function categoryOptionLabel(id: string): string {
  const zh = CREDENTIAL_CATEGORY_ZH_LABELS[id as keyof typeof CREDENTIAL_CATEGORY_ZH_LABELS];
  return `${zh || id}（${id}）`;
}

export function typeOptionLabel(item: CredentialTypeItem, customSuffix: string): string {
  return `${item.name}（${item.key}）${item.is_builtin ? '' : ` · ${customSuffix}`}`;
}

export function namePlaceholderForType(typeKey: string | undefined, fallback: string): string {
  const placeholders: Record<string, string> = {
    ssh: '例如：生产跳板机 SSH',
    sql: '例如：生产 MySQL 只读',
    snmp: '例如：核心交换机 SNMP',
    cloud: '例如：华为云只读 AK',
    winrm: '例如：Windows Server 凭据',
  };
  return (typeKey && placeholders[typeKey]) || fallback;
}

export function inferredCategory(
  types: CredentialTypeItem[],
  category?: string,
  type?: string,
): string | undefined {
  if (category) {
    return category;
  }
  return types.find((item) => item.key === type)?.categories?.[0];
}

export interface CredentialQuickCreateFormProps {
  form: FormInstance;
  types: CredentialTypeItem[];
  groups?: CredentialGroupOption[];
  lockedCategory?: boolean;
  lockedType?: boolean;
  typeMismatch?: boolean;
  hideOrganization?: boolean;
}

export const CredentialQuickCreateForm: React.FC<CredentialQuickCreateFormProps> = ({
  form,
  types,
  groups = [],
  lockedCategory,
  lockedType,
  typeMismatch,
  hideOrganization = false,
}) => {
  const { t } = useTranslation();
  const watchedCategory = Form.useWatch('category', form);
  const watchedType = Form.useWatch('type', form);
  const selectedType = types.find((item) => item.key === watchedType);
  const lockHint = t('system.credential.taskLockedHint', '当前任务已指定，不可修改。');
  const extra = (locked: boolean | undefined) => (locked ? (
    <span className="text-xs text-[var(--color-text-3)]">{lockHint}</span>
  ) : null);

  const categoryIds = Array.from(new Set([
    ...CREDENTIAL_CATEGORIES,
    ...types.flatMap((item) => item.categories),
  ]));
  const typeOptions = types
    .filter((item) => !watchedCategory || item.categories.includes(watchedCategory))
    .map((item) => ({
      value: item.key,
      label: typeOptionLabel(item, t('system.credential.custom')),
    }));

  return (
    <Form form={form} layout="vertical">
      <div className="grid grid-cols-2 gap-x-4">
        <Form.Item
          name="category"
          label={t('system.credential.categoryBelong')}
          extra={extra(lockedCategory)}
          rules={[{ required: true }]}
        >
          <Select
            disabled={lockedCategory}
            options={categoryIds.map((id) => ({ value: id, label: categoryOptionLabel(id) }))}
            onChange={(next) => {
              const first = types.find((item) => item.categories.includes(next));
              form.setFieldsValue({ type: first?.key, fields: {} });
            }}
          />
        </Form.Item>
        <Form.Item
          name="type"
          label={t('system.credential.credentialType')}
          extra={extra(lockedType)}
          rules={[{ required: true }]}
        >
          <Select
            disabled={lockedType}
            options={typeMismatch ? [] : typeOptions}
            onChange={() => form.setFieldsValue({ fields: {} })}
          />
        </Form.Item>
      </div>
      <Form.Item name="name" label={t('system.credential.credentialName')} rules={[{ required: true, whitespace: true }]}>
        <Input placeholder={namePlaceholderForType(watchedType, t('system.credential.credentialNamePlaceholder'))} />
      </Form.Item>
      {hideOrganization ? (
        <Form.Item name="group_id" hidden rules={[{ required: true }]}>
          <Input />
        </Form.Item>
      ) : (
        <Form.Item name="group_id" label={t('system.credential.organizationBelong')} rules={[{ required: true }]}>
          <Select options={groups.map((item) => ({ value: item.id, label: item.name }))} />
        </Form.Item>
      )}
      {selectedType ? (
        <CredentialFieldsBlock key={selectedType.key} fields={selectedType.fields} form={form} />
      ) : (
        <p className="mb-0 text-xs text-[var(--color-text-3)]">{t('system.credential.selectTypeFirst', '请先选择凭据类型')}</p>
      )}
    </Form>
  );
};
