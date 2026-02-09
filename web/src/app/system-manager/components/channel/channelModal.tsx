'use client';
import React, { useState, useEffect } from 'react';
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

  const fetchChannelDetail = async (id: string) => {
    setLoading(true);
    try {
      const data = await getChannelDetail(id);
      setChannelData(data);
      setOriginalSmtpPwd(data.config?.smtp_pwd);
      setOriginalWebhookUrl(data.config?.webhook_url);
      form.setFieldsValue({
        ...data,
        ...data.config
      });
    } catch {
      message.error(t('common.fetchFailed'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!visible) return;
    form.resetFields();
    if (type === 'edit' && channelId) {
      fetchChannelDetail(channelId);
    } else {
      setChannelData({
        name: '',
        channel_type: channelType,
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
        } : {
          webhook_url: '',
        },
      });
    }
  }, [type, channelId, visible]);

  const handleOk = async () => {
    try {
      setConfirmLoading(true);
      const values = await form.validateFields();
      const { name, description, team, smtp_pwd, webhook_url, ...config } = values;

      // Exclude smtp_pwd and webhook_url if they haven't changed
      const finalConfig = {
        ...config,
        ...(smtp_pwd !== originalSmtpPwd ? { smtp_pwd } : {}),
        ...(webhook_url !== originalWebhookUrl ? { webhook_url } : {}),
      };

      const payload = {
        channel_type: channelType,
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
    if (['smtp_pwd', 'webhook_url'].includes(key)) {
      return 'editablePwd';
    }
    if (key === 'timeout') {
      return 'number';
    }
    return 'input';
  };

  const formFields = React.useMemo(() => {
    if (!channelData.config) return [];

    const basicFields = [
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

    const configFields = Object.keys(channelData.config).map((key) => ({
      name: key,
      type: getFieldType(key),
      label: t(`system.channel.settings.${key}`),
      placeholder: `${t('common.inputMsg')}${t(`system.channel.settings.${key}`)}`,
      initialValue: ['smtp_usessl', 'smtp_usetls'].includes(key) ? false : undefined,
      rules: [{ required: !['smtp_usessl', 'smtp_usetls'].includes(key), message: `${t('common.inputMsg')}${t(`system.channel.settings.${key}`)}` }],
    }));

    return [...basicFields, ...configFields];
  }, [channelData.config, t]);

  return (
    <OperateModal
      title={type === 'add' ? t('system.channel.settings.addChannel') : t('system.channel.settings.editChannel')}
      visible={visible}
      onOk={handleOk}
      onCancel={handleCancel}
      confirmLoading={confirmLoading}
    >
      {loading ? (
        <div className="w-full flex items-center justify-center">
          <Spin />
        </div>
      ) : (
        <DynamicForm
          form={form}
          fields={formFields}
        />
      )}
    </OperateModal>
  );
};

export default ChannelModal;
