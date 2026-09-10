'use client';

import React from 'react';
import { Form, Input, InputNumber, Select } from 'antd';
import type { FormInstance } from 'antd/es/form';
import { useTranslation } from '@/utils/i18n';
import type { CredentialFieldSchema } from './types';
import { isCredentialFieldVisible } from './visibleWhen';
import { parseEnumValues } from './enumValues';

export function fieldLabel(field: CredentialFieldSchema): string {
  return field.name || field.id;
}

export function CredentialFieldsBlock({
  fields,
  form,
  readOnly,
  secretPlaceholder,
}: {
  fields: CredentialFieldSchema[];
  form: FormInstance;
  readOnly?: boolean;
  secretPlaceholder?: string;
}) {
  Form.useWatch('fields', form);
  return <>{renderCredentialFields(fields, form, { readOnly, secretPlaceholder })}</>;
}

export function renderCredentialFields(
  fields: CredentialFieldSchema[],
  form: FormInstance,
  options?: { readOnly?: boolean; secretPlaceholder?: string },
) {
  const values = (form.getFieldsValue(true) as Record<string, unknown>) || {};
  const nested = (values.fields as Record<string, unknown> | undefined) || {};
  return fields
    .filter((field) => isCredentialFieldVisible(field, nested))
    .map((field) => (
      <CredentialDynamicField
        key={field.id}
        field={field}
        readOnly={options?.readOnly}
        secretPlaceholder={options?.secretPlaceholder}
      />
    ));
}

interface CredentialDynamicFieldProps {
  field: CredentialFieldSchema;
  readOnly?: boolean;
  secretPlaceholder?: string;
}

const CredentialDynamicField: React.FC<CredentialDynamicFieldProps> = ({
  field,
  readOnly,
  secretPlaceholder,
}) => {
  const { t } = useTranslation();
  const label = fieldLabel(field);
  const required = Boolean(field.required) && (field.kind !== 'secret' || field.widget === 'textarea');
  const secretRequired = Boolean(field.required) && field.kind === 'secret' && field.widget !== 'textarea' && !readOnly;

  if (field.kind === 'secret' && field.widget !== 'textarea') {
    return (
      <Form.Item
        name={['fields', field.id]}
        label={label}
        initialValue={field.default}
        rules={secretRequired && !readOnly ? [{ required: true }] : undefined}
      >
        <Input.Password
          disabled={readOnly}
          autoComplete="new-password"
          placeholder={
            readOnly
              ? secretPlaceholder || t('system.credential.secretSaved')
              : secretPlaceholder || t('system.credential.secretLeaveBlank')
          }
        />
      </Form.Item>
    );
  }

  if (field.widget === 'textarea') {
    return (
      <Form.Item
        name={['fields', field.id]}
        label={label}
        initialValue={field.default}
        rules={required ? [{ required: true, whitespace: true }] : undefined}
      >
        <Input.TextArea disabled={readOnly} rows={4} />
      </Form.Item>
    );
  }

  if (field.kind === 'enum') {
    return (
      <Form.Item
        name={['fields', field.id]}
        label={label}
        initialValue={field.default}
        rules={required ? [{ required: true }] : undefined}
      >
        <Select
          disabled={readOnly}
          options={parseEnumValues(field.values).map((value) => ({ label: value, value }))}
        />
      </Form.Item>
    );
  }

  if (field.kind === 'number') {
    const numericDefault = field.default === undefined || field.default === '' ? undefined : Number(field.default);
    return (
      <Form.Item
        name={['fields', field.id]}
        label={label}
        initialValue={typeof numericDefault === 'number' && Number.isFinite(numericDefault) ? numericDefault : undefined}
        rules={required ? [{ required: true }] : undefined}
      >
        <InputNumber disabled={readOnly} className="w-full" />
      </Form.Item>
    );
  }

  return (
    <Form.Item
      name={['fields', field.id]}
      label={label}
      initialValue={field.default}
      rules={required ? [{ required: true, whitespace: true }] : undefined}
    >
      <Input disabled={readOnly} />
    </Form.Item>
  );
};
