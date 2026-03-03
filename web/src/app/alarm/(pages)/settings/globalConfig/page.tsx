'use client';

import React, { useState, useEffect } from 'react';
import PermissionWrapper from '@/components/permission';
import { useSettingApi } from '@/app/alarm/api/settings';
import { useCommon } from '@/app/alarm/context/common';
import { useTranslation } from '@/utils/i18n';
import {
  Config,
  GlobalConfig,
  ChannelItem,
  NotifyOption,
} from '@/app/alarm/types/settings';
import {
  Card,
  Typography,
  Form,
  InputNumber,
  Select,
  Checkbox,
  Button,
  Space,
  Switch,
  Spin,
} from 'antd';

export default function UnallocatedNotificationConfig() {
  const { t } = useTranslation();
  const { userList } = useCommon();
  const [editMode, setEditMode] = useState(false);
  const [expanded, setExpanded] = useState(true);
  const [form] = Form.useForm<Config>();
  const [loading, setLoading] = useState(false);
  const [activationLoading, setActivationLoading] = useState(false);
  const [globalConfigId, setGlobalConfigId] = useState<string | number>('');
  const [updateLoading, setUpdateLoading] = useState(false);
  const [notifyOptions, setNotifyOptions] = useState<NotifyOption[]>([]);
  const [channelList, setChannelList] = useState<ChannelItem[]>([]);
  const [channelLoading, setChannelLoading] = useState(false);
  const {
    getGlobalConfig,
    updateGlobalConfig,
    toggleGlobalConfig,
    getChannelList,
  } = useSettingApi();
  const [config, setConfig] = useState<Config>({
    notify_every: 60,
    notify_people: [],
    notify_channel: [],
  });

  const assigneeOptions = userList.map((u) => ({
    label: `${u.display_name} (${u.username})`,
    value: u.username,
  }));

  // 获取通知渠道列表
  const fetchChannelList = async () => {
    setChannelLoading(true);
    try {
      const data: any = await getChannelList({});
      setChannelList(data);
      const options: NotifyOption[] = data.map((channel: ChannelItem) => ({
        label: channel.name,
        value: channel.id.toString(),
      }));
      setNotifyOptions(options);
    } catch (error) {
      console.error('获取通知渠道失败:', error);
    } finally {
      setChannelLoading(false);
    }
  };

  useEffect(() => {
    form.setFieldsValue(config);
  }, [form, config]);

  useEffect(() => {
    const loadGlobalConfig = async () => {
      setLoading(true);
      try {
        const res: GlobalConfig = await getGlobalConfig(
          'no_dispatch_alert_notice',
        );
        const { notify_channel, notify_every, notify_people } = res.value;

        const notifyChannelIds = (notify_channel || []).map((ch: any) =>
          ch.id.toString(),
        );

        form.setFieldsValue({
          notify_channel: notifyChannelIds,
          notify_every,
          notify_people,
        });
        setConfig({
          notify_channel: notifyChannelIds,
          notify_every,
          notify_people,
        });
        setExpanded(res.is_activate ?? false);
        setGlobalConfigId(res.id);
      } catch (error) {
        console.error('加载全局配置失败', error);
      } finally {
        setLoading(false);
      }
    };

    // 获取通知渠道列表
    fetchChannelList();
    loadGlobalConfig();
  }, []);

  const enterEdit = () => {
    setEditMode(true);
  };

  const cancelEdit = () => {
    form.setFieldsValue(config);
    setEditMode(false);
  };

  const confirmEdit = async () => {
    setUpdateLoading(true);
    try {
      const values = await form.validateFields();

      const notifyChannels = (values.notify_channel || [])
        .map((id: string) => channelList.find((ch) => ch.id.toString() === id))
        .filter(Boolean);

      await updateGlobalConfig(globalConfigId, {
        key: 'no_dispatch_alert_notice',
        is_activate: true,
        value: {
          notify_channel: notifyChannels,
          notify_every: values.notify_every,
          notify_people: values.notify_people,
        },
      });
      setConfig(values);
      setEditMode(false);
    } catch (error) {
      console.error('更新配置失败', error);
    } finally {
      setUpdateLoading(false);
    }
  };

  const handleToggleActivation = async (checked: boolean) => {
    setActivationLoading(true);
    try {
      await toggleGlobalConfig(globalConfigId, { is_activate: checked });
      setExpanded(checked);
    } catch (error) {
      console.error('切换激活状态失败', error);
    } finally {
      setActivationLoading(false);
    }
  };

  return (
    <Card style={{ height: '100%' }}>
      {loading ? (
        <div className="flex justify-center pt-[20px] mt-[20vh]">
          <Spin spinning={loading} />
        </div>
      ) : (
        <div className="h-full w-[600px]">
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              marginBottom: 10,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center' }}>
              <div
                style={{
                  width: 4,
                  height: 16,
                  backgroundColor: '#1890ff',
                  marginRight: 8,
                }}
              />
              <Typography.Title
                level={4}
                style={{ margin: 0, fontSize: '16px' }}
              >
                {t('settings.globalConfig.title')}
              </Typography.Title>
            </div>
            <Switch
              size="small"
              className="ml-[24px]"
              checked={expanded}
              loading={activationLoading}
              onChange={(checked) => handleToggleActivation(checked)}
            />
          </div>
          {expanded && (
            <div className="ml-[12px]">
              <div className="mb-[20px] text-[var(--color-text-3)]">
                {t('settings.globalConfig.description')}
              </div>
              <Form
                form={form}
                layout="horizontal"
                initialValues={config}
                style={{ maxWidth: 500 }}
              >
                <Form.Item
                  name="notify_every"
                  label={t('settings.globalConfig.intervalLabel')}
                  rules={[
                    {
                      required: true,
                      message:
                        t('common.inputTip') +
                        t('settings.globalConfig.intervalLabel'),
                    },
                  ]}
                >
                  <InputNumber
                    min={1}
                    addonAfter={t('settings.globalConfig.intervalMinutes')}
                    disabled={!editMode}
                    style={{ width: '160px' }}
                  />
                </Form.Item>

                <Form.Item
                  name="notify_people"
                  label={t('settings.globalConfig.personnelLabel')}
                  rules={[
                    {
                      required: true,
                      message:
                        t('common.selectTip') +
                        t('settings.globalConfig.personnelLabel'),
                    },
                  ]}
                >
                  <Select
                    mode="multiple"
                    showSearch
                    allowClear
                    options={assigneeOptions}
                    disabled={!editMode}
                    placeholder={t(
                      'settings.globalConfig.personnelPlaceholder'
                    )}
                    filterOption={(input: string, option?: any) =>
                      !!option?.label
                        ?.toLowerCase()
                        .includes(input.toLowerCase())
                    }
                  />
                </Form.Item>

                <Form.Item
                  name="notify_channel"
                  label={t('settings.globalConfig.notificationMethodLabel')}
                  rules={[
                    {
                      required: true,
                      message:
                        t('common.selectTip') +
                        t('settings.globalConfig.notificationMethodLabel'),
                    },
                  ]}
                >
                  <Checkbox.Group
                    options={notifyOptions}
                    disabled={!editMode || channelLoading}
                  />
                  {channelLoading && (
                    <div className="flex justify-center h-[32px] mt-2">
                      <Spin spinning={channelLoading} />
                    </div>
                  )}
                </Form.Item>

                <Form.Item>
                  <Space>
                    {editMode ? (
                      <>
                        <Button
                          type="primary"
                          onClick={confirmEdit}
                          loading={updateLoading}
                        >
                          {t('common.confirm')}
                        </Button>
                        <Button onClick={cancelEdit}>
                          {t('common.cancel')}
                        </Button>
                      </>
                    ) : (
                      <PermissionWrapper requiredPermissions={['Edit']}>
                        <Button type="primary" onClick={enterEdit}>
                          {t('common.edit')}
                        </Button>
                      </PermissionWrapper>
                    )}
                  </Space>
                </Form.Item>
              </Form>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
