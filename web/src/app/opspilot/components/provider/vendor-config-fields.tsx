'use client';

import React from 'react';
import { Form, Input, Switch } from 'antd';
import type { FormInstance } from 'antd';
import { useTranslation } from '@/utils/i18n';
import Password from '@/components/password';
import GroupTreeSelect from '@/components/group-tree-select';
import type { ModelVendorPayload } from '@/app/opspilot/types/provider';

export interface OpspilotProviderVendorConfigFieldsProps {
  form: FormInstance<ModelVendorPayload>;
  mode: 'add' | 'edit';
  variant: 'modal' | 'detail';
  apiKeyChanged: boolean;
  apiKeyValue?: string;
  apiKeyAction?: React.ReactNode;
  onApiBaseChange?: () => void;
  onApiKeyReset: () => void;
  onApiKeyChange: (value: string) => void;
}

const OpspilotProviderVendorConfigFields: React.FC<OpspilotProviderVendorConfigFieldsProps> = ({
  form,
  mode,
  variant,
  apiKeyChanged,
  apiKeyValue,
  apiKeyAction,
  onApiBaseChange,
  onApiKeyReset,
  onApiKeyChange,
}) => {
  const { t } = useTranslation();
  const isModal = variant === 'modal';
  const sharedItemClassName = isModal ? 'mb-5' : undefined;

  const apiKeyField = (
    <Form.Item
      name="api_key"
      rules={mode === 'add' || apiKeyChanged ? [{ required: true, message: t('provider.vendor.apiKeyRequired') }] : []}
      className={apiKeyAction ? 'mb-0 flex-1' : undefined}
    >
      <Password
        value={apiKeyValue}
        placeholder={t('provider.vendor.apiKeyRequired')}
        clickToEdit={mode === 'edit'}
        onReset={onApiKeyReset}
        onChange={onApiKeyChange}
      />
    </Form.Item>
  );

  return (
    <>
      <Form.Item
        name="name"
        label={t('common.name')}
        rules={[{ required: true, message: t('provider.vendor.nameRequired') }]}
        extra={isModal ? <span className="text-xs">{t('provider.vendor.nameHelp')}</span> : undefined}
        className={sharedItemClassName}
      >
        <Input className={isModal ? 'text-sm' : undefined} placeholder={t('provider.vendor.namePlaceholder')} />
      </Form.Item>

      <Form.Item
        name="api_base"
        label={t('provider.vendor.apiBase')}
        rules={[{ required: true, message: t('provider.vendor.apiBaseRequired') }]}
        extra={isModal ? <span className="text-xs">{t('provider.vendor.apiBaseHelp')}</span> : undefined}
        className={sharedItemClassName}
      >
        <Input
          placeholder={t('provider.vendor.apiBasePlaceholder')}
          onChange={onApiBaseChange}
        />
      </Form.Item>

      <Form.Item
        label={t('provider.vendor.apiKey')}
        required
        className={sharedItemClassName}
      >
        {apiKeyAction ? (
          <div className="flex items-start gap-3">
            {apiKeyField}
            {apiKeyAction}
          </div>
        ) : apiKeyField}
      </Form.Item>

      <Form.Item
        name="team"
        label={t('common.organization')}
        rules={[{ required: true, message: t('provider.vendor.groupRequired') }]}
        className={sharedItemClassName}
      >
        <GroupTreeSelect
          value={form.getFieldValue('team') || []}
          onChange={(value) => form.setFieldValue('team', value)}
          placeholder={t('provider.vendor.groupPlaceholder')}
          multiple
        />
      </Form.Item>

      <Form.Item
        name="enabled"
        label={isModal ? t('common.enable') : t('provider.vendor.enabledStatus')}
        valuePropName="checked"
        className={sharedItemClassName}
      >
        <Switch size="small" />
      </Form.Item>

      <Form.Item
        name="description"
        label={t('provider.vendor.description')}
        className={isModal ? 'mb-0' : undefined}
      >
        <Input.TextArea rows={4} placeholder={t('provider.vendor.descriptionPlaceholder')} />
      </Form.Item>
    </>
  );
};

export default OpspilotProviderVendorConfigFields;
