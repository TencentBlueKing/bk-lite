'use client';

import React, { useEffect, useRef } from 'react';
import { DatePicker, Form, Input, Radio } from 'antd';
import { InfoCircleOutlined } from '@ant-design/icons';
import type { Dayjs } from 'dayjs';
import dayjs from 'dayjs';
import OperateFormModal from '@/components/operate-form-modal';
import { useTranslation } from '@/utils/i18n';
import { isDuplicateTokenNameError } from '@/app/system-manager/utils/openapiTokens';
import OpenApiTokenScopeFields from './OpenApiTokenScopeFields';
import type {
  OpenApiTokenCreateFormValues,
  OpenApiTokenExpiryPreset,
  OpenApiTokenServiceCatalog,
  OpenApiTokenTab,
} from './types';

const SYSTEM_ID_PATTERN = /^[a-z][a-z0-9-]{0,31}$/;

const inferExpiryPreset = (expiresAt?: unknown): OpenApiTokenExpiryPreset => (
  expiresAt ? 'custom' : 'never'
);

const resolveExpiresAt = (
  preset: OpenApiTokenExpiryPreset,
  customValue: unknown,
): Dayjs | undefined => {
  if (preset === 'never') {
    return undefined;
  }
  if (preset === '1m') {
    return dayjs().add(1, 'month');
  }
  if (preset === '3m') {
    return dayjs().add(3, 'month');
  }
  return customValue ? dayjs(customValue as string).endOf('day') : undefined;
};

interface OpenApiTokenCreateModalProps {
  open: boolean;
  kind: OpenApiTokenTab;
  catalog: OpenApiTokenServiceCatalog[];
  editing?: boolean;
  initialValues?: OpenApiTokenCreateFormValues;
  submitting?: boolean;
  onSubmit: (values: OpenApiTokenCreateFormValues) => void | Promise<unknown>;
  onCancel: () => void;
}

const OpenApiTokenCreateModal: React.FC<OpenApiTokenCreateModalProps> = ({
  open,
  kind,
  catalog,
  editing = false,
  initialValues,
  submitting = false,
  onSubmit,
  onCancel,
}) => {
  const { t } = useTranslation();
  const [form] = Form.useForm<OpenApiTokenCreateFormValues>();
  const isSystem = kind === 'system';
  const expiryPreset = Form.useWatch('expiryPreset', form) as OpenApiTokenExpiryPreset | undefined;
  const hydratedKey = useRef<string | null>(null);
  const recordKey = !open
    ? 'closed'
    : (editing ? `edit:${initialValues?.systemId ?? ''}:${initialValues?.name ?? ''}` : `create:${kind}`);

  useEffect(() => {
    if (!open) {
      hydratedKey.current = null;
      return;
    }
    if (hydratedKey.current === recordKey) {
      return;
    }
    hydratedKey.current = recordKey;
    if (editing && initialValues) {
      form.setFieldsValue({
        name: initialValues.name,
        systemId: initialValues.systemId,
        expiryPreset: inferExpiryPreset(initialValues.expiresAt),
        expiresAt: initialValues.expiresAt
          ? dayjs(initialValues.expiresAt as string)
          : undefined,
        scopeMode: initialValues.scopeMode,
        scopeEndpoints: initialValues.scopeEndpoints || [],
      });
      return;
    }
    form.setFieldsValue({
      name: undefined,
      systemId: undefined,
      expiryPreset: 'never',
      expiresAt: undefined,
      scopeMode: undefined,
      scopeEndpoints: [],
    });
  }, [editing, form, initialValues, kind, open, recordKey]);

  const handleConfirm = async () => {
    const values = await form.validateFields();
    const preset = values.expiryPreset ?? 'never';
    try {
      await onSubmit({
        ...values,
        expiresAt: resolveExpiresAt(preset, values.expiresAt),
      });
    } catch (error) {
      if (isDuplicateTokenNameError(error)) {
        form.setFields([{
          name: 'name',
          errors: [t('system.settings.secret.nameExists')],
        }]);
      }
    }
  };

  const title = editing
    ? (isSystem
      ? t('system.settings.secret.editSystemTitle')
      : t('system.settings.secret.editPersonalTitle'))
    : (isSystem
      ? t('system.settings.secret.createSystemTitle')
      : t('system.settings.secret.createPersonalTitle'));

  const expiryOptions = [
    { label: t('system.settings.secret.expiryNever'), value: 'never' },
    { label: t('system.settings.secret.expiryThreeMonths'), value: '3m' },
    { label: t('system.settings.secret.expiryOneMonth'), value: '1m' },
    { label: t('system.settings.secret.expiryCustom'), value: 'custom' },
  ];

  return (
    <OperateFormModal
      open={open}
      width={800}
      title={title}
      confirmText={t('common.confirm')}
      cancelText={t('common.cancel')}
      confirmLoading={submitting}
      cancelDisabled={submitting}
      primaryFirst={false}
      onConfirm={() => {
        void handleConfirm();
      }}
      onCancel={onCancel}
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={{ expiryPreset: 'never', scopeEndpoints: [] }}
        className="mt-1"
      >
        {editing ? (
          <div className="mb-4 flex items-center gap-2 rounded-md border border-[var(--color-border-2)] bg-[var(--color-fill-1)] px-3 py-2 text-xs text-[var(--color-text-2)]">
            <InfoCircleOutlined className="shrink-0 text-[var(--color-primary)]" />
            <span>{t('system.settings.secret.editHint')}</span>
          </div>
        ) : null}
        {isSystem ? (
          <Form.Item
            name="systemId"
            label={t('system.settings.secret.systemId')}
            extra={
              <span className="text-xs text-[var(--color-text-3)]">
                {editing
                  ? t('system.settings.secret.systemIdLocked')
                  : t('system.settings.secret.systemIdHelp')}
              </span>
            }
            rules={[
              { required: true, message: t('system.settings.secret.systemId') },
              {
                pattern: SYSTEM_ID_PATTERN,
                message: t('system.settings.secret.systemIdHelp'),
              },
            ]}
          >
            <Input
              disabled={editing}
              placeholder={t('system.settings.secret.systemIdPlaceholder')}
              className="font-mono"
            />
          </Form.Item>
        ) : null}
        <Form.Item
          name="name"
          label={t('system.settings.secret.name')}
          rules={[{ required: true, message: t('common.inputRequired') }]}
        >
          <Input placeholder={t('system.settings.secret.namePlaceholder')} />
        </Form.Item>
        <Form.Item
          name="expiryPreset"
          label={t('system.settings.secret.expiresAt')}
          className={expiryPreset === 'custom' ? '!mb-2' : undefined}
        >
          <Radio.Group
            options={expiryOptions}
            onChange={(event) => {
              if (event.target.value !== 'custom') {
                form.setFieldValue('expiresAt', undefined);
              }
            }}
          />
        </Form.Item>
        {expiryPreset === 'custom' ? (
          <div className="mb-6 rounded-md border border-[var(--color-border-2)] bg-[var(--color-fill-1)] p-3">
            <Form.Item
              name="expiresAt"
              className="!mb-0"
              rules={[{
                required: true,
                message: t('system.settings.secret.expiresAtRequired'),
              }]}
            >
              <DatePicker
                className="w-full max-w-xs"
                format="YYYY-MM-DD"
                disabledDate={(current) => current.isBefore(dayjs().startOf('day'))}
              />
            </Form.Item>
          </div>
        ) : null}
        <OpenApiTokenScopeFields catalog={catalog} />
      </Form>
    </OperateFormModal>
  );
};

export default OpenApiTokenCreateModal;
