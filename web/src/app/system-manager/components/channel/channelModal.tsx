'use client';
import React, { useState, useEffect, useRef } from 'react';
import { useSearchParams } from 'next/navigation';
import { Form, message, Spin } from 'antd';
import { useTranslation } from '@/utils/i18n';
import DynamicForm from '@/components/dynamic-form';
import OperateModal from '@/components/operate-modal'
import { useChannelApi } from '@/app/system-manager/api/channel';
import { ChannelType } from '@/app/system-manager/types/channel';

interface ChannelModalProps {
  visible: boolean;
  onClose: () => void;
  type: 'add' | 'edit';
  channelId: string | null;
  onSuccess: () => void;
}

const WEBHOOK_SUB_TYPES: ChannelType[] = ['enterprise_wechat_bot', 'feishu_bot', 'dingtalk_bot', 'custom_webhook'];

const isWebhookSubType = (ct: string): boolean => WEBHOOK_SUB_TYPES.includes(ct as ChannelType);

const getDefaultConfig = (st: ChannelType): Record<string, unknown> => {
  switch (st) {
    case 'feishu_bot':
    case 'dingtalk_bot':
      return { webhook_url: '', sign_secret: '' };
    case 'custom_webhook':
      return { webhook_url: '', request_method: 'POST', headers: '', body_template: '' };
    case 'enterprise_wechat_bot':
    default:
      return { webhook_url: '' };
  }
};

const getMergedConfig = (st: ChannelType, serverConfig: Record<string, unknown>): Record<string, unknown> => {
  const defaults = getDefaultConfig(st);
  return { ...defaults, ...serverConfig };
};

const ChannelModal: React.FC<ChannelModalProps> = ({
  visible,
  onClose,
  type,
  channelId,
  onSuccess,
}) => {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const searchParams = useSearchParams();
  const channelType = (searchParams?.get('id') || 'email') as ChannelType;
  const { addChannel, updateChannel, getChannelDetail } = useChannelApi();
  const [loading, setLoading] = useState<boolean>(false);
  const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
  const [channelData, setChannelData] = useState<any>({ config: {} });
  const [originalSmtpPwd, setOriginalSmtpPwd] = useState<string | undefined>(undefined);
  const [originalWebhookUrl, setOriginalWebhookUrl] = useState<string | undefined>(undefined);
  const [originalSignSecret, setOriginalSignSecret] = useState<string | undefined>(undefined);
  const [subType, setSubType] = useState<ChannelType>('enterprise_wechat_bot');
  const [pendingFormFill, setPendingFormFill] = useState<Record<string, unknown> | null>(null);
  const isFillingForm = useRef<boolean>(false);

  const isWebhookChannel = channelType === 'enterprise_wechat_bot';

  const watchedSubType = Form.useWatch('sub_type', form);
  useEffect(() => {
    if (!isWebhookChannel || !watchedSubType || isFillingForm.current) return;
    if (watchedSubType as ChannelType !== subType) {
      const newSt = watchedSubType as ChannelType;
      setSubType(newSt);
      const newConfig = getDefaultConfig(newSt);
      setChannelData((prev: any) => ({
        ...prev,
        channel_type: newSt,
        config: newConfig,
      }));
      const basicValues = form.getFieldsValue(['name', 'description', 'team']);
      form.setFieldsValue({ ...basicValues, sub_type: newSt, ...newConfig });
    }
  }, [watchedSubType]);

  const fetchChannelDetail = async (id: string) => {
    setLoading(true);
    try {
      const data = await getChannelDetail(id);
      setOriginalSmtpPwd(data.config?.smtp_pwd);
      setOriginalWebhookUrl(data.config?.webhook_url);
      setOriginalSignSecret(data.config?.sign_secret);
      const actualType = data.channel_type as ChannelType;
      const resolvedSubType = (isWebhookChannel && isWebhookSubType(actualType))
        ? actualType
        : 'enterprise_wechat_bot';
      if (isWebhookChannel) {
        setSubType(resolvedSubType);
      }
      const mergedConfig = isWebhookChannel
        ? getMergedConfig(resolvedSubType, data.config || {})
        : data.config;
      const enrichedData = { ...data, config: mergedConfig };
      setChannelData(enrichedData);
      const formValues: Record<string, unknown> = {
        name: data.name,
        description: data.description,
        team: data.team,
        ...mergedConfig,
      };
      if (isWebhookChannel) {
        formValues.sub_type = resolvedSubType;
      }
      setPendingFormFill(formValues);
    } catch {
      message.error(t('common.fetchFailed'));
    } finally {
      setLoading(false);
    }
  };

  // Deferred form fill: runs after channelData update causes formFields recompute and field registration
  useEffect(() => {
    if (!pendingFormFill) return;
    isFillingForm.current = true;
    requestAnimationFrame(() => {
      form.setFieldsValue(pendingFormFill);
      setPendingFormFill(null);
      requestAnimationFrame(() => {
        isFillingForm.current = false;
      });
    });
  }, [pendingFormFill, form]);

  useEffect(() => {
    if (!visible) return;
    form.resetFields();
    setPendingFormFill(null);
    isFillingForm.current = false;
    setOriginalSmtpPwd(undefined);
    setOriginalWebhookUrl(undefined);
    setOriginalSignSecret(undefined);
    const defaultSubType: ChannelType = 'enterprise_wechat_bot';
    if (isWebhookChannel) {
      setSubType(defaultSubType);
    }
    if (type === 'edit' && channelId) {
      fetchChannelDetail(channelId);
    } else {
      setChannelData({
        name: '',
        channel_type: isWebhookChannel ? defaultSubType : channelType,
        description: '',
        config: channelType === 'email' ? {
          smtp_server: '',
          port: '',
          smtp_user: '',
          smtp_pwd: '',
          smtp_usessl: false,
          smtp_usetls: false,
          mail_sender: '',
        } : channelType === 'nats' ? {
          namespace: '',
          method_name: '',
          timeout: 60,
        } : getDefaultConfig(defaultSubType),
      });
    }
  }, [type, channelId, visible]);

  const handleOk = async () => {
    try {
      setConfirmLoading(true);
      const values = await form.validateFields();
      const {
        name, description, team,
        smtp_pwd, webhook_url, sign_secret,
        request_method, headers, body_template,
        ...config
      } = values;

      delete config.sub_type;

      const finalConfig: Record<string, unknown> = { ...config };

      if (smtp_pwd !== undefined && smtp_pwd !== originalSmtpPwd) {
        finalConfig.smtp_pwd = smtp_pwd;
      }
      if (webhook_url !== undefined && webhook_url !== originalWebhookUrl) {
        finalConfig.webhook_url = webhook_url;
      }
      if (sign_secret !== undefined && sign_secret !== originalSignSecret) {
        finalConfig.sign_secret = sign_secret;
      }
      if (request_method !== undefined) {
        finalConfig.request_method = request_method;
      }
      if (headers !== undefined) {
        finalConfig.headers = headers;
      }
      if (body_template !== undefined) {
        finalConfig.body_template = body_template;
      }

      const effectiveChannelType = isWebhookChannel ? subType : channelType;

      const payload = {
        channel_type: effectiveChannelType,
        name,
        description,
        team,
        config: finalConfig,
      };

      if (type === 'add') {
        await addChannel(payload);
      } else if (type === 'edit' && channelId) {
        await updateChannel({ id: channelId, ...payload });
      }
      message.success(t('common.saveSuccess'));
      onSuccess();
      onClose();
    } catch (error: any) {
      if (error.errorFields && error.errorFields.length) {
        const firstFieldErrorMessage = error.errorFields[0].errors[0];
        message.error(firstFieldErrorMessage || t('common.valFailed'));
      } else {
        message.error(t('common.saveFailed'));
      }
    } finally {
      setConfirmLoading(false);
    }
  };

  const handleCancel = () => {
    onClose();
  };

  const getFieldType = (key: string): string => {
    if (['smtp_usessl', 'smtp_usetls'].includes(key)) {
      return 'switch';
    }
    if (['smtp_pwd', 'webhook_url', 'sign_secret'].includes(key)) {
      return 'editablePwd';
    }
    if (key === 'timeout') {
      return 'inputNumber';
    }
    if (key === 'request_method') {
      return 'select';
    }
    if (['body_template', 'headers'].includes(key)) {
      return 'textarea';
    }
    return 'input';
  };

  const formFields = React.useMemo(() => {
    if (!channelData.config) return [];

    const basicFields: any[] = [
      {
        name: 'name',
        type: 'input',
        label: t('system.channel.settings.name'),
        placeholder: `${t('common.inputMsg')}${t('system.channel.settings.name')}`,
        rules: [{ required: true, message: `${t('common.inputMsg')}${t('system.channel.settings.name')}` }],
      },
      {
        name: 'description',
        type: 'textarea',
        label: t('system.channel.settings.description'),
        placeholder: `${t('common.inputMsg')}${t('system.channel.settings.description')}`,
        rows: 4,
        rules: [{ required: true, message: `${t('common.inputMsg')}${t('system.channel.settings.description')}` }],
      },
      {
        name: 'team',
        type: 'groupTreeSelect',
        label: t('system.channel.settings.team'),
        placeholder: `${t('common.selectMsg')}${t('system.channel.settings.team')}`,
        rules: [{ required: true, message: `${t('common.selectMsg')}${t('system.channel.settings.team')}` }],
      },
    ];

    if (isWebhookChannel) {
      basicFields.push({
        name: 'sub_type',
        type: 'select',
        label: t('system.channel.settings.sub_type'),
        placeholder: `${t('common.selectMsg')}${t('system.channel.settings.sub_type')}`,
        rules: [{ required: true, message: `${t('common.selectMsg')}${t('system.channel.settings.sub_type')}` }],
        options: [
          { value: 'enterprise_wechat_bot', label: t('system.channel.settings.subTypeEnterpriseWechat') },
          { value: 'feishu_bot', label: t('system.channel.settings.subTypeFeishu') },
          { value: 'dingtalk_bot', label: t('system.channel.settings.subTypeDingtalk') },
          { value: 'custom_webhook', label: t('system.channel.settings.subTypeCustom') },
        ],
      });
    }

    const configFields = Object.keys(channelData.config).map((key) => {
      const nonRequiredKeys = ['smtp_usessl', 'smtp_usetls', 'sign_secret', 'headers'];
      const fieldDef: Record<string, unknown> = {
        name: key,
        type: getFieldType(key),
        label: t(`system.channel.settings.${key}`),
        placeholder: `${t('common.inputMsg')}${t(`system.channel.settings.${key}`)}`,
        initialValue: ['smtp_usessl', 'smtp_usetls'].includes(key) ? false : undefined,
        rules: [{ required: !nonRequiredKeys.includes(key), message: `${t('common.inputMsg')}${t(`system.channel.settings.${key}`)}` }],
      };

      if (key === 'request_method') {
        fieldDef.options = [
          { value: 'POST', label: 'POST' },
          { value: 'GET', label: 'GET' },
        ];
      }

      if (key === 'body_template') {
        fieldDef.rows = 4;
        fieldDef.placeholder = t('system.channel.settings.bodyTemplateHint');
      }

      if (key === 'headers') {
        fieldDef.rows = 4;
      }

      return fieldDef;
    });

    return [...basicFields, ...configFields];
  }, [channelData.config, t, isWebhookChannel]);

  return (
    <OperateModal
      title={type === 'add' ? t('system.channel.settings.addChannel') : t('system.channel.settings.editChannel')}
      visible={visible}
      onOk={handleOk}
      onCancel={handleCancel}
      confirmLoading={confirmLoading}
    >
      <Spin spinning={loading}>
        <DynamicForm
          form={form}
          fields={formFields}
        />
      </Spin>
    </OperateModal>
  );
};

export default ChannelModal;
