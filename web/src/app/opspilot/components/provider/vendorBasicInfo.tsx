'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { Button, Form, Input, Select, Skeleton, Switch, message } from 'antd';
import { useTranslation } from '@/utils/i18n';
import Password from '@/components/password';
import GroupTreeSelect from '@/components/group-tree-select';
import { VENDOR_LABEL_MAP, VENDOR_OPTIONS } from '@/app/opspilot/constants/provider';
import type { ModelVendor, ModelVendorPayload } from '@/app/opspilot/types/provider';
import { useProviderApi } from '@/app/opspilot/api/provider';

const MASKED_API_KEY = '*******';

interface VendorBasicInfoSubmitValues extends Omit<ModelVendorPayload, 'api_key'> {
  api_key?: string;
}

interface VendorBasicInfoProps {
  vendorId: number;
  onUpdated: (vendor: ModelVendor) => void;
}

const VendorBasicInfo: React.FC<VendorBasicInfoProps> = ({ vendorId, onUpdated }) => {
  const [form] = Form.useForm<ModelVendorPayload>();
  const { t } = useTranslation();
  const { fetchVendorDetail, updateVendor, testVendorConnection } = useProviderApi();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [apiKeyChanged, setApiKeyChanged] = useState(false);
  const apiKeyValue = Form.useWatch('api_key', form);

  const onUpdatedRef = React.useRef(onUpdated);
  onUpdatedRef.current = onUpdated;

  const loadVendor = useCallback(async () => {
    setLoading(true);
    try {
      const detail = await fetchVendorDetail(vendorId);
      setApiKeyChanged(false);
      form.setFieldsValue({
        name: detail.name,
        vendor_type: detail.vendor_type,
        api_base: detail.api_base,
        api_key: MASKED_API_KEY,
        team: detail.team || [],
        description: detail.description || '',
        enabled: detail.enabled ?? true,
      });
      onUpdatedRef.current(detail);
    } catch {
      message.error(t('common.fetchFailed'));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vendorId]);

  useEffect(() => {
    loadVendor();
  }, [loadVendor]);

  const handleSave = async () => {
    const values = await form.validateFields();
    const payload: VendorBasicInfoSubmitValues = {
      name: values.name,
      vendor_type: values.vendor_type,
      api_base: values.api_base,
      team: values.team,
      description: values.description,
      enabled: values.enabled,
    };

    if (apiKeyChanged) {
      payload.api_key = values.api_key;
    }

    setSaving(true);
    try {
      const updatedVendor = await updateVendor(vendorId, payload);
      onUpdated(updatedVendor);
      if (apiKeyChanged) {
        setApiKeyChanged(false);
        form.setFieldValue('api_key', MASKED_API_KEY);
      }
      message.success(t('common.updateSuccess'));
    } catch {
      message.error(t('common.updateFailed'));
    } finally {
      setSaving(false);
    }
  };

  const handleTestConnection = async () => {
    try {
      const fieldsToValidate: Array<keyof ModelVendorPayload> = ['api_base'];
      if (apiKeyChanged) {
        fieldsToValidate.push('api_key');
      }

      const values = await form.validateFields(fieldsToValidate);
      setTesting(true);
      const result = await testVendorConnection({
        api_base: values.api_base,
        api_key: apiKeyChanged ? values.api_key : undefined,
        password_changed: apiKeyChanged,
        original_id: apiKeyChanged ? vendorId : vendorId,
      });

      if (result.success) {
        message.success(t('provider.vendor.testSuccess'));
        return;
      }

      message.error(t('provider.vendor.testFailed'));
    } catch (error: any) {
      if (error?.errorFields) {
        message.error(t('provider.vendor.validationError'));
      }
    } finally {
      setTesting(false);
    }
  };

  if (loading) {
    return <Skeleton active paragraph={{ rows: 8 }} />;
  }

  return (
    <div>
      <div className="mb-4">
        <div className="text-sm font-medium" style={{ color: 'var(--color-text-1)' }}>{t('provider.vendor.detailTitle')}</div>
        <div className="mt-1 text-xs" style={{ color: 'var(--color-text-3)' }}>{t('provider.vendor.detailDescription')}</div>
      </div>

      <Form form={form} layout="vertical">
        <div className="grid grid-cols-1 gap-x-4 xl:grid-cols-2">
          <Form.Item
            name="name"
            label={t('common.name')}
            rules={[{ required: true, message: t('provider.vendor.nameRequired') }]}
          >
            <Input placeholder={t('provider.vendor.namePlaceholder')} />
          </Form.Item>

          <Form.Item
            name="vendor_type"
            label={t('provider.vendor.typeLabel')}
            rules={[{ required: true, message: t('provider.vendor.vendorTypeRequired') }]}
          >
            <Select options={VENDOR_OPTIONS.map((option) => ({ label: VENDOR_LABEL_MAP[option.value], value: option.value }))} />
          </Form.Item>
        </div>

        <Form.Item
          name="api_base"
          label={t('provider.vendor.apiBase')}
          rules={[{ required: true, message: t('provider.vendor.apiBaseRequired') }]}
        >
          <Input placeholder={t('provider.vendor.apiBasePlaceholder')} />
        </Form.Item>

        <Form.Item
          label={t('provider.vendor.apiKey')}
          required
        >
          <div className="flex items-start gap-3">
            <Form.Item
              name="api_key"
              rules={apiKeyChanged ? [{ required: true, message: t('provider.vendor.apiKeyRequired') }] : []}
              className="mb-0 flex-1"
            >
              <Password
                value={apiKeyValue}
                placeholder={t('provider.vendor.apiKeyRequired')}
                clickToEdit
                onReset={() => {
                  setApiKeyChanged(true);
                  form.setFieldValue('api_key', '');
                }}
                onChange={(value) => {
                  setApiKeyChanged(true);
                  form.setFieldValue('api_key', value);
                }}
              />
            </Form.Item>
            <Button className="mt-px" loading={testing} onClick={handleTestConnection}>
              {t('provider.vendor.testConnection')}
            </Button>
          </div>
        </Form.Item>

        <Form.Item
          name="team"
          label={t('common.organization')}
          rules={[{ required: true, message: t('provider.vendor.groupRequired') }]}
        >
          <GroupTreeSelect
            value={form.getFieldValue('team') || []}
            onChange={(value) => form.setFieldValue('team', value)}
            placeholder={t('provider.vendor.groupPlaceholder')}
            multiple
          />
        </Form.Item>

        <Form.Item
          name="description"
          label={t('provider.vendor.description')}
        >
          <Input.TextArea rows={4} placeholder={t('provider.vendor.descriptionPlaceholder')} />
        </Form.Item>

        <Form.Item
          name="enabled"
          label={t('provider.vendor.enabledStatus')}
          valuePropName="checked"
        >
          <Switch size="small" />
        </Form.Item>

        <div className="flex justify-end gap-3 pt-4">
          <Button loading={testing} onClick={handleTestConnection}>
            {t('provider.vendor.testConnection')}
          </Button>
          <Button type="primary" loading={saving} onClick={handleSave}>
            {t('common.save')}
          </Button>
        </div>
      </Form>
    </div>
  );
};

export default VendorBasicInfo;
