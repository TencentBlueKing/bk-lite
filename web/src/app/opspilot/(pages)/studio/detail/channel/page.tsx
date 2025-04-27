'use client';

import React, { useEffect, useState } from 'react';
import { Input, Switch, Button, Form, Spin, message } from 'antd';
import Icon from '@/components/icon';
import { useTranslation } from '@/utils/i18n';
import { useSearchParams } from 'next/navigation';
import { useStudioApi } from '@/app/opspilot/api/studio';
import { ChannelProps } from '@/app/opspilot/types/studio';
import OperateModal from '@/components/operate-modal';
import PermissionWrapper from '@/components/permission';

const ChannelPage: React.FC = () => {
  const { t } = useTranslation();
  const { fetchChannels, updateChannel } = useStudioApi();
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [currentApp, setCurrentApp] = useState<Partial<ChannelProps>>({});
  const [open, setOpen] = useState(false);
  const [fields, setFields] = useState<{ [key: string]: string }>({});
  const [loading, setLoading] = useState(false);
  const [switchLoading, setSwitchLoading] = useState<{ [key: string]: boolean }>({});
  const [formLoading, setFormLoading] = useState(false);
  const [apps, setApps] = useState<ChannelProps[]>([]);
  const [currentChannelType, setCurrentChannelType] = useState<string>('');
  const [confirmLoading, setConfirmLoading] = useState(false);
  const searchParams = useSearchParams();
  const botId = searchParams ? searchParams.get('id') : null;

  const IconMap: any = {
    enterprise_wechat: 'qiwei2',
    wechat_official_account: 'weixingongzhonghao',
    ding_talk: 'dingding',
    web: 'icon-08',
    deepseek: 'a-deepseek1'
  };

  const fetchData = async () => {
    try {
      setLoading(true);
      const data = await fetchChannels(botId);
      const appsData = data.map((channel: any) => ({
        id: channel.id,
        name: channel.name,
        enabled: channel.enabled,
        icon: IconMap[channel.channel_type] || 'wangye',
        channel_config: channel.channel_config,
      }));
      setApps(appsData);
    } catch {
      message.error(t('common.fetchFailed'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleOpenModal = (app: ChannelProps) => {
    setCurrentApp(app);
    setOpen(app.enabled);
    setCurrentChannelType(Object.keys(app.channel_config)[0]);

    setFormLoading(true);
    const fetchedFields = { ...app.channel_config[Object.keys(app.channel_config)[0]] };
    setFields(fetchedFields);
    setFormLoading(false);
    setIsModalVisible(true);
  };

  const handleCloseModal = () => {
    setIsModalVisible(false);
    setCurrentApp({});
    setFields({});
  };

  const handleConfirmModal = async () => {
    const updatedConfig = {
      id: currentApp.id,
      enabled: open,
      channel_config: {
        [currentChannelType]: fields,
      },
    };

    try {
      setConfirmLoading(true);
      await updateChannel(updatedConfig);
      message.success(t('common.saveSuccess'));
      handleCloseModal();
      await fetchData();
    } catch {
      message.error(t('common.updateFailed'));
    } finally {
      setConfirmLoading(false);
    }
  };

  const handleSwitchChange = async (checked: boolean, app: ChannelProps) => {
    setSwitchLoading(prev => ({ ...prev, [app.id]: true }));

    try {
      await updateChannel({ id: app.id, enabled: checked });
      const updatedApps = apps.map(a => a.id === app.id ? { ...a, enabled: checked } : a);
      setApps(updatedApps);
      message.success(t('common.updateSuccess'));
    } catch {
      message.error(t('common.updateFailed'));
    } finally {
      setSwitchLoading(prev => ({ ...prev, [app.id]: false }));
    }
  };

  const sensitiveKeys = ['client_secret', 'aes_key', 'secret', 'token'];

  return (
    <div className="flex flex-wrap justify-start">
      {loading ? (
        <Spin size="large" className="m-auto" />
      ) : (
        apps.map((app) => (
          <div key={app.id} className="w-full sm:w-1/3 p-4">
            <div
              className='border shadow-sm hover:shadow-md transition-shadow duration-300 ease-in-out rounded-lg p-4 relative cursor-pointer group'>
              <div className="absolute top-2 right-2">
                <PermissionWrapper requiredPermissions={['Setting']}>
                  <Switch
                    size="small"
                    checked={app.enabled}
                    loading={switchLoading[app.id] || false}
                    checkedChildren={t('common.open')}
                    unCheckedChildren={t('common.close')}
                    onChange={(checked) => handleSwitchChange(checked, app)}
                  />
                </PermissionWrapper>
              </div>
              <div className="flex justify-center items-center space-x-4 my-10">
                <Icon type={app.icon} className="text-4xl" />
                <h2 className="text-lg font-bold m-0">{app.name}</h2>
              </div>
              <div className="w-full h-[32px] flex justify-center items-end">
                <PermissionWrapper className="w-full" requiredPermissions={['Setting']}>
                  <Button
                    type="primary"
                    className="w-full rounded-md transition-opacity duration-300"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleOpenModal(app);
                    }}
                  >
                    <Icon type="shezhi" /> {t('studio.channel.setting')}
                  </Button>
                </PermissionWrapper>
              </div>
            </div>
          </div>
        ))
      )}

      <OperateModal
        title={t('studio.channel.setting')}
        visible={isModalVisible}
        onCancel={handleCloseModal}
        footer={[
          <Button key="cancel" onClick={handleCloseModal}>{t('common.cancel')}</Button>,
          <Button key="confirm" type="primary" loading={confirmLoading} onClick={handleConfirmModal}>{t('common.confirm')}</Button>,
        ]}
      >
        {formLoading ? (
          <div className="flex items-center">
            <Spin size="large" className="m-auto" />
          </div>
        ) : (
          <Form layout="vertical" style={{ padding: '16px 0' }}>
            {Object.keys(fields).map((key) => (
              <Form.Item key={key} label={key.replace(/_/g, ' ')}>
                {sensitiveKeys.some(sensitiveKey => key.toLowerCase().includes(sensitiveKey)) ? (
                  <Input.Password
                    value={fields[key]}
                    visibilityToggle={false}
                    onChange={(e) => setFields({ ...fields, [key]: e.target.value })}
                    onCopy={(e) => e.preventDefault()}
                    onCut={(e) => e.preventDefault()}
                    autoComplete="new-password"
                  />
                ) : (
                  <Input
                    value={fields[key]}
                    onChange={(e) => setFields({ ...fields, [key]: e.target.value })}
                    autoComplete="off"
                  />
                )}
              </Form.Item>
            ))}
          </Form>
        )}
      </OperateModal>
    </div>
  );
};

export default ChannelPage;
