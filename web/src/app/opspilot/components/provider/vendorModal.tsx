import React, {useEffect, useState} from 'react';
import {Alert, Button, Form, Input, message, Radio, Switch} from 'antd';
import Image from 'next/image';
import {useTranslation} from '@/utils/i18n';
import {useUserInfoContext} from '@/context/userInfo';
import OperateModal from '@/components/operate-modal';
import Password from '@/components/password';
import GroupTreeSelect from '@/components/group-tree-select';
import {useProviderApi} from '@/app/opspilot/api/provider';
import {
  getAnthropicApiBase,
  getDefaultProtocolType,
  getVendorOption,
  PROTOCOL_TYPE_OPTIONS,
  supportsProtocolSelection,
  VENDOR_LABEL_MAP,
  VENDOR_OPTIONS
} from '@/app/opspilot/constants/provider';
import type {ModelVendor, ModelVendorPayload, ProtocolType} from '@/app/opspilot/types/provider';

interface VendorModalSubmitValues extends Omit<ModelVendorPayload, 'api_key'> {
  api_key?: string;
}

const MASKED_API_KEY = '*******';

interface VendorModalProps {
  visible: boolean;
  mode: 'add' | 'edit';
  vendor?: ModelVendor | null;
  confirmLoading: boolean;
  onOk: (values: VendorModalSubmitValues) => Promise<ModelVendor | void>;
  onCancel: () => void;
}

const VendorModal: React.FC<VendorModalProps> = ({
  visible,
  mode,
  vendor,
  confirmLoading,
  onOk,
  onCancel,
}) => {
  const [form] = Form.useForm<ModelVendorPayload>();
  const { t } = useTranslation();
  const { selectedGroup } = useUserInfoContext();
  const { testVendorConnection, fetchVendorDetail } = useProviderApi();
  const [apiBaseTouched, setApiBaseTouched] = useState(false);
  const [apiKeyChanged, setApiKeyChanged] = useState(false);
  const [submitError, setSubmitError] = useState<string>('');
  const [testing, setTesting] = useState(false);
  const vendorType = Form.useWatch('vendor_type', form);
  const protocolType = Form.useWatch('protocol_type', form);
  const apiKeyValue = Form.useWatch('api_key', form);
  const fetchVendorDetailRef = React.useRef(fetchVendorDetail);
  const translationRef = React.useRef(t);

  fetchVendorDetailRef.current = fetchVendorDetail;
  translationRef.current = t;

  useEffect(() => {
    if (!visible) {
      return;
    }

    setApiBaseTouched(false);
    setApiKeyChanged(false);
    setSubmitError('');

    if (mode === 'edit' && vendor) {
      let cancelled = false;

      form.setFieldsValue({
        name: vendor.name,
        vendor_type: vendor.vendor_type,
        protocol_type: vendor.protocol_type || getDefaultProtocolType(vendor.vendor_type),
        api_base: vendor.api_base,
        api_key: MASKED_API_KEY,
        team: vendor.team || [],
        description: vendor.description || '',
        enabled: vendor.enabled ?? true,
      });

      fetchVendorDetailRef.current(vendor.id)
        .then((detail) => {
          if (cancelled) {
            return;
          }

          form.setFieldsValue({
            name: detail.name,
            vendor_type: detail.vendor_type,
            protocol_type: detail.protocol_type || getDefaultProtocolType(detail.vendor_type),
            api_base: detail.api_base,
            api_key: MASKED_API_KEY,
            team: detail.team || [],
            description: detail.description || '',
            enabled: detail.enabled ?? true,
          });
        })
        .catch(() => {
          if (!cancelled) {
            message.error(translationRef.current('common.fetchFailed'));
          }
        });

      return () => {
        cancelled = true;
      };

      return;
    }

    const defaultVendor = VENDOR_OPTIONS[0];
    form.resetFields();
    form.setFieldsValue({
      vendor_type: defaultVendor.value,
      protocol_type: getDefaultProtocolType(defaultVendor.value),
      api_base: defaultVendor.defaultApiBase,
      team: selectedGroup ? [Number(selectedGroup.id)] : [],
      enabled: true,
    });
    // Only reinitialize when dialog mode/source data changes.
  }, [visible, mode, vendor, form, selectedGroup]);

  useEffect(() => {
    if (!visible || mode !== 'add' || apiBaseTouched || !vendorType) {
      return;
    }

    const option = getVendorOption(vendorType);
    if (option) {
      form.setFieldValue('api_base', option.defaultApiBase);
      // 更新默认协议类型
      form.setFieldValue('protocol_type', getDefaultProtocolType(vendorType));
    }
  }, [apiBaseTouched, form, mode, vendorType, visible]);

  // 当协议类型变化时，更新默认 API 地址
  useEffect(() => {
    if (!visible || mode !== 'add' || apiBaseTouched || !protocolType || !supportsProtocolSelection(vendorType)) {
      return;
    }

    if (protocolType === 'anthropic') {
      // 根据供应商类型获取对应的 Anthropic API 地址
      form.setFieldValue('api_base', getAnthropicApiBase(vendorType));
    } else {
      // OpenAI 协议使用供应商默认地址
      const option = getVendorOption(vendorType);
      form.setFieldValue('api_base', option?.defaultApiBase || '');
    }
  }, [apiBaseTouched, form, mode, protocolType, vendorType, visible]);

  const handleOk = async () => {
    try {
      setSubmitError('');
      const values = await form.validateFields();
      const payload: VendorModalSubmitValues = {
        name: values.name,
        vendor_type: values.vendor_type,
        protocol_type: supportsProtocolSelection(values.vendor_type) ? values.protocol_type : undefined,
        api_base: values.api_base,
        team: values.team,
        description: values.description,
        enabled: values.enabled,
      };

      if (mode === 'add' || apiKeyChanged) {
        payload.api_key = values.api_key;
      }

      await onOk(payload);
    } catch (error: any) {
      if (error?.errorFields) {
        setSubmitError(t('provider.vendor.validationError'));
        message.error(t('provider.vendor.validationError'));
        return;
      }

      throw error;
    }
  };

  const handleTestConnection = async () => {
    try {
      setSubmitError('');
      const fieldsToValidate = ['api_base'] as Array<keyof ModelVendorPayload>;
      if (mode === 'add' || apiKeyChanged) {
        fieldsToValidate.push('api_key');
      }

      const values = await form.validateFields(fieldsToValidate);
      const currentVendorType = form.getFieldValue('vendor_type');
      const currentProtocolType = form.getFieldValue('protocol_type') as ProtocolType;
      
      // 确定实际使用的协议类型
      let effectiveProtocolType: ProtocolType = 'openai';
      if (currentVendorType === 'anthropic') {
        effectiveProtocolType = 'anthropic';
      } else if (supportsProtocolSelection(currentVendorType) && currentProtocolType) {
        effectiveProtocolType = currentProtocolType;
      }

      setTesting(true);
      const result = await testVendorConnection({
        api_base: values.api_base,
        api_key: mode === 'add' || apiKeyChanged ? values.api_key : undefined,
        password_changed: mode === 'add' ? true : apiKeyChanged,
        original_id: mode === 'edit' && vendor ? vendor.id : undefined,
        protocol_type: effectiveProtocolType,
        vendor_type: currentVendorType,
      });
      if (result.success) {
        message.success(t('provider.vendor.testSuccess'));
        return;
      }

      message.error(result.message || t('provider.vendor.testFailed'));
    } catch (error: any) {
      if (error?.errorFields) {
        setSubmitError(t('provider.vendor.validationError'));
        message.error(t('provider.vendor.validationError'));
        return;
      }

      setSubmitError(error?.message || t('provider.vendor.testFailed'));
    } finally {
      setTesting(false);
    }
  };

  return (
    <OperateModal
      title={t(mode === 'add' ? 'provider.vendor.addTitle' : 'provider.vendor.editTitle')}
      visible={visible}
      width={680}
      confirmLoading={confirmLoading}
      onOk={handleOk}
      onCancel={onCancel}
      footer={[
        <Button key="cancel" onClick={onCancel}>
          {t('common.cancel')}
        </Button>,
        <Button key="test" onClick={handleTestConnection} loading={testing}>
          {t('provider.vendor.testConnection')}
        </Button>,
        <Button key="save" type="primary" onClick={handleOk} loading={confirmLoading}>
          {t('common.save')}
        </Button>,
      ]}
      destroyOnClose
    >
      <Form form={form} layout="vertical" className="pb-1">
        {submitError ? <Alert className="mb-4" type="error" message={submitError} showIcon /> : null}

        <Form.Item
          name="vendor_type"
          label={t('provider.vendor.vendorType')}
          rules={[{ required: true, message: t('provider.vendor.vendorTypeRequired') }]}
          className="mb-5"
        >
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {VENDOR_OPTIONS.map((option) => {
              const selected = vendorType === option.value;

              return (
                <button
                  key={option.value}
                  type="button"
                  className="flex flex-col items-center gap-3 rounded-2xl border px-3 py-4 transition-all duration-200"
                  style={{
                    borderColor: selected ? 'var(--color-primary)' : 'var(--color-border-2)',
                    background: selected ? 'rgba(45, 107, 255, 0.08)' : 'var(--color-bg)',
                  }}
                  onClick={() => form.setFieldValue('vendor_type', option.value)}
                >
                  <Image
                    src={`/app/models/${option.icon}.svg`}
                    alt={option.label}
                    width={28}
                    height={28}
                    className="object-contain"
                  />
                  <span className="text-sm font-medium" style={{ color: 'var(--color-text-1)' }}>{VENDOR_LABEL_MAP[option.value]}</span>
                </button>
              );
            })}
          </div>
        </Form.Item>

        {/* 协议类型选择 - 仅在 vendor_type 为 'other' 时显示 */}
        {supportsProtocolSelection(vendorType) && (
          <Form.Item
            name="protocol_type"
            label={t('provider.vendor.protocolType')}
            rules={[{ required: true, message: t('provider.vendor.protocolTypeRequired') }]}
            className="mb-5"
          >
            <Radio.Group>
              {PROTOCOL_TYPE_OPTIONS.map((option) => (
                <Radio key={option.value} value={option.value}>
                  {option.label}
                </Radio>
              ))}
            </Radio.Group>
          </Form.Item>
        )}

        <Form.Item
          name="name"
          label={t('common.name')}
          rules={[{ required: true, message: t('provider.vendor.nameRequired') }]}
          extra={<span className="text-xs">{t('provider.vendor.nameHelp')}</span>}
          className="mb-5"
        >
          <Input className="text-sm" placeholder={t('provider.vendor.namePlaceholder')} />
        </Form.Item>

        <Form.Item
          name="api_base"
          label={t('provider.vendor.apiBase')}
          rules={[{ required: true, message: t('provider.vendor.apiBaseRequired') }]}
          extra={<span className="text-xs">{t('provider.vendor.apiBaseHelp')}</span>}
          className="mb-5"
        >
          <Input
            placeholder={t('provider.vendor.apiBasePlaceholder')}
            onChange={() => setApiBaseTouched(true)}
          />
        </Form.Item>

        <Form.Item
          name="api_key"
          label={t('provider.vendor.apiKey')}
          rules={mode === 'add' || apiKeyChanged ? [{ required: true, message: t('provider.vendor.apiKeyRequired') }] : []}
          className="mb-5"
        >
          <Password
            value={apiKeyValue}
            placeholder={t('provider.vendor.apiKeyRequired')}
            clickToEdit={mode === 'edit'}
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

        <Form.Item
          name="team"
          label={t('common.organization')}
          rules={[{ required: true, message: t('provider.vendor.groupRequired') }]}
          className="mb-5"
        >
          <GroupTreeSelect
            value={form.getFieldValue('team') || []}
            onChange={(value) => form.setFieldValue('team', value)}
            placeholder={t('provider.vendor.groupPlaceholder')}
            multiple
          />
        </Form.Item>

        <Form.Item name="enabled" label={t('common.enable')} valuePropName="checked" className="mb-5">
          <Switch size="small" />
        </Form.Item>

        <Form.Item name="description" label={t('provider.vendor.description')} className="mb-0">
          <Input.TextArea rows={4} placeholder={t('provider.vendor.descriptionPlaceholder')} />
        </Form.Item>
      </Form>
    </OperateModal>
  );
};

export default VendorModal;
