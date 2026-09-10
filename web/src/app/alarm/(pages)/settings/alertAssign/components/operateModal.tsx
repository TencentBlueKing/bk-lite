'use client';

import { invalidMatchRules } from '@/app/alarm/utils/multivalueRules';

import React, { useEffect, useState } from 'react';
import './operateModal.scss';
import MatchRule from '@/app/alarm/(pages)/settings/components/matchRule';
import EffectiveTime, {
  defaultEffectiveTime,
} from '@/app/alarm/(pages)/settings/components/effectiveTime';
import { useCommon } from '@/app/alarm/context/common';
import { useTranslation } from '@/utils/i18n';
import { CaretRightOutlined } from '@ant-design/icons';
import { useSettingApi } from '@/app/alarm/api/settings';
import EscalationChain from './escalationChain';
import NotificationTargetFields from './notificationTargetFields';
import {
  buildNotificationTarget,
  getNotificationTargetFormValue,
} from './notificationTarget';
import LevelIcon from '@/app/alarm/components/levelIcon';
import { ChannelItem, NotifyOption } from '@/app/alarm/types/settings';
import {
  buildChannelsWithTemplateBindings,
  getNotificationTemplateBindings,
  NotificationTemplateOption,
} from './notificationTemplateBinding';
import { getNotificationTemplateChannel } from '@/app/alarm/utils/notificationTemplateChannels';
import {
  Tag,
  Form,
  Input,
  Checkbox,
  Button,
  Drawer,
  Radio,
  Collapse,
  InputNumber,
  message,
  Space,
  Spin,
  Select,
  Typography,
  Alert,
} from 'antd';

interface OperateModalProps {
  open: boolean;
  currentRow?: any;
  onClose: () => void;
  onSuccess?: () => void;
}

const OperateModalPage: React.FC<OperateModalProps> = ({
  open,
  currentRow,
  onClose,
  onSuccess,
}) => {
  const { t } = useTranslation();
  const { levelList, levelMap, userList } = useCommon();
  const { createAssignment, updateAssignment, getChannelList, getNotificationTemplateOptions } =
    useSettingApi();

  const personnelOptions = userList.map(({ display_name, username }) => ({
    label: `${display_name} (${username})`,
    value: username,
  }));

  const [form] = Form.useForm();
  const [messageApi, messageContextHolder] = message.useMessage();
  const [submitLoading, setSubmitLoading] = useState(false);
  const [notifyOptions, setNotifyOptions] = useState<NotifyOption[]>([]);
  const [channelList, setChannelList] = useState<ChannelItem[]>([]);
  const [channelLoading, setChannelLoading] = useState(false);
  const [channelLoadFailed, setChannelLoadFailed] = useState(false);
  const [templateOptions, setTemplateOptions] = useState<Record<string, NotificationTemplateOption[]>>({});
  const [templateLoading, setTemplateLoading] = useState(false);

  // 获取通知渠道列表
  const fetchChannelList = async () => {
    setChannelLoading(true);
    setChannelLoadFailed(false);
    setChannelList([]);
    setNotifyOptions([]);
    setTemplateOptions({});
    setTemplateLoading(false);
    let data: ChannelItem[];
    try {
      data = await getChannelList({}) as ChannelItem[];
      setChannelList(data);
      const options: NotifyOption[] = data.map((channel: ChannelItem) => ({
        label: channel.name,
        value: channel.id.toString(),
      }));
      setNotifyOptions(options);
      if (!currentRow && data.length > 0) {
        form.setFieldsValue({
          notify_channels: [data[0].id.toString()],
        });
      }
    } catch {
      setChannelLoadFailed(true);
      return;
    } finally {
      setChannelLoading(false);
    }
    setTemplateLoading(true);
    try {
      const channelTypes = Array.from(new Set(data.map((channel: ChannelItem) => channel.channel_type)));
      const optionGroups = await Promise.all(
        channelTypes.map(async (channelType) => {
          const templates = await getNotificationTemplateOptions({ channel_type: channelType });
          return [
            channelType,
            (templates || []).map((template: { id: number; name: string }) => ({ label: template.name, value: template.id })),
          ] as const;
        }),
      );
      setTemplateOptions(Object.fromEntries(optionGroups));
    } catch (error) {
      console.error('获取通知模板失败:', error);
    } finally {
      setTemplateLoading(false);
    }
  };

  const handleClose = () => {
    form.resetFields();
    onClose();
  };

  useEffect(() => {
    if (open) {
      fetchChannelList();

      if (currentRow) {
        const notifyChannelIds = (currentRow.notify_channels || []).map(
          (ch: any) => ch.id.toString(),
        );

        const targetFormValue = getNotificationTargetFormValue(
          currentRow.config?.notification_target,
          currentRow.personnel,
        );
        form.setFieldsValue({
          ...currentRow,
          ...targetFormValue,
          notify_channels: notifyChannelIds,
          notification_templates: getNotificationTemplateBindings(currentRow.notify_channels || []),
          notification_frequency: currentRow.notification_frequency,
          match_rules:
            currentRow.match_type === 'filter'
              ? currentRow.match_rules
              : undefined,
          config: {
            ...currentRow.config,
            start_time: currentRow.config?.start_time,
            end_time: currentRow.config?.end_time,
          },
          escalation: currentRow.config?.escalation
            ? {
              ...currentRow.config.escalation,
              layers: (currentRow.config.escalation.layers || []).map(
                (l: any) => ({
                  ...l,
                  ...getNotificationTargetFormValue(
                    l.notification_target,
                    l.personnel,
                  ),
                  notify_channels: (l.notify_channels || []).map((ch: any) =>
                    ch.id.toString()
                  ),
                })
              ),
            }
            : { enabled: false },
        });
      } else {
        form.resetFields();
        form.setFieldsValue({
          priority: 100,
          config: defaultEffectiveTime,
          target_type: 'user',
        });
      }
    }
  }, [open, currentRow, form]);

  const ruleType = Form.useWatch('match_type', form);
  const escalationEnabled = Form.useWatch(['escalation', 'enabled'], form);
  const selectedChannelIds: string[] = Form.useWatch('notify_channels', form) || [];
  const channelCheckOptions = notifyOptions;

  const onFinish = async (values: any) => {
    setSubmitLoading(true);
    try {
      const params = getParams(values);
      if (currentRow?.id) {
        await updateAssignment(currentRow.id, params);
      } else {
        await createAssignment(params);
      }
      messageApi.success(
        currentRow ? t('alarmCommon.successOperate') : t('common.addSuccess')
      );
      form.resetFields();
      onClose();
      onSuccess && onSuccess();
    } catch {
      messageApi.error(t('alarmCommon.operateFailed'));
    } finally {
      setSubmitLoading(false);
    }
  };

  const getParams = (values: any) => {
    const notifyChannels = buildChannelsWithTemplateBindings(
      values.notify_channels || [],
      channelList,
      values.notification_templates,
    );

    const notificationTarget = buildNotificationTarget(values);
    const params: any = {
      name: values.name,
      priority: values.priority,
      match_type: values.match_type,
      notify_channels: notifyChannels,
      personnel:
        notificationTarget.type === 'user'
          ? notificationTarget.usernames
          : [],
      config: {
        ...(values.config || defaultEffectiveTime),
        notification_target: notificationTarget,
      },
      match_rules: values.match_type === 'filter' ? values.match_rules : [],
    };

    if (values.notification_scenario) {
      params.notification_scenario = values.notification_scenario;
    }
    if (values.notification_frequency) {
      const freqObj: Record<string, any> = {};
      Object.entries(values.notification_frequency).forEach(
        ([levelId, val]: any) => {
          freqObj[levelId] = {
            interval_minutes: val.interval_minutes || 0,
            max_count: 0,
          };
        }
      );
      params.notification_frequency = freqObj;
    }
    const esc = values.escalation;
    if (esc?.enabled) {
      const layers = (esc.layers || []).map((l: any) => ({
        personnel:
          l.target_type === 'organization' ? [] : l.personnel || [],
        notification_target: buildNotificationTarget(l),
        wait_minutes: l.wait_minutes || 0,
        notify_channels: buildChannelsWithTemplateBindings(
          l.notify_channels || [],
          channelList,
          values.notification_templates,
        ),
      }));
      params.config = {
        ...params.config,
        // 当前仅支持累加模式（不提供替换）；后端仍兼容 replace，此处固定 append
        escalation: { enabled: true, mode: 'append', layers },
      };
      // B 模型：分派人员是初始第一棒，与升级层各自独立，不再相互覆盖
    } else {
      params.config = { ...params.config, escalation: { enabled: false } };
    }
    return params;
  };

  return (
    <>
      {messageContextHolder}
      <Drawer
      title={
        currentRow
          ? t('settings.assignStrategy.editTitle') + ` - ${currentRow.name}`
          : t('settings.assignStrategy.addTitle')
      }
      placement="right"
      width={740}
      open={open}
      onClose={handleClose}
      maskClosable={false}
      footer={
        <div style={{ textAlign: 'right' }}>
          <Button
            type="primary"
            loading={submitLoading}
            onClick={() => form.submit()}
          >
            {t('settings.assignStrategy.submit')}
          </Button>
          <Button style={{ marginLeft: 8 }} onClick={handleClose}>
            {t('common.cancel')}
          </Button>
        </div>
      }
    >
      <Form
        form={form}
        layout="vertical"
        onFinish={onFinish}
      >
        <Form.Item
          name="name"
          label={t('settings.assignName')}
          rules={[
            {
              required: true,
              message: t('common.inputTip'),
            },
          ]}
        >
          <Input placeholder={t('common.inputTip')} />
        </Form.Item>
        <Form.Item
          initialValue="all"
          name="match_type"
          label={t('settings.assignStrategy.formMatchingRules')}
          rules={[{ required: true, message: t('common.inputTip') }]}
        >
          <Radio.Group className="mt-1">
            <Radio value="all">{t('settings.assignStrategy.ruleAll')}</Radio>
            <Radio value="filter">
              {t('settings.assignStrategy.ruleFilter')}
            </Radio>
          </Radio.Group>
        </Form.Item>

        {ruleType === 'filter' && (
          <Form.Item
            name="match_rules"
            validateTrigger={[]}
            className="mb-6"
            rules={[
              {
                validator: (_, value: any[][]) => {
                  if (invalidMatchRules(value, false, "assignment")) {
                    return Promise.reject(new Error(t('common.inputTip')));
                  }
                  return Promise.resolve();
                },
              },
            ]}
          >
            <MatchRule scope="assignment"
              monitorSourceField="push_source_ids"
              levelType="alert"

            />
          </Form.Item>
        )}

        <Form.Item
          name="priority"
          label={t('settings.assignStrategy.priority')}
          initialValue={100}
          extra={t('settings.assignStrategy.priorityHelp')}
          rules={[{ required: true, message: t('common.inputTip') }]}
        >
          <InputNumber
            aria-label={t('settings.assignStrategy.priority')}
            min={0}
            max={100}
            precision={0}
            className="w-[150px]"
          />
        </Form.Item>

        <NotificationTargetFields
          personnelOptions={personnelOptions}
          typeLabel={t('settings.assignStrategy.formTargetSelect')}
        />
        <Form.Item
          label={t('settings.assignStrategy.formNotifyMethod')}
          required
        >
          <div>
            <Form.Item
              name="notify_channels"
              noStyle
              rules={[{ required: true, message: t('common.selectTip') }]}
            >
              <Checkbox.Group options={notifyOptions} disabled={channelLoading} />
            </Form.Item>
            {channelLoading && (
              <div className="flex h-[32px] justify-center">
                <Spin spinning={channelLoading} />
              </div>
            )}
            {!channelLoading && channelLoadFailed && (
              <Alert
                type="error"
                showIcon
                message={t('settings.assignStrategy.channelLoadFailed')}
                action={<Button size="small" onClick={fetchChannelList}>{t('settings.assignStrategy.retryChannels')}</Button>}
              />
            )}
            {!channelLoading && !channelLoadFailed && notifyOptions.length === 0 && (
              <Alert
                type="info"
                showIcon
                message={t('settings.assignStrategy.noChannels')}
                description={
                  <div className="flex flex-col items-start gap-2">
                    <span>{t('settings.assignStrategy.noChannelsDescription')}</span>
                    <Space>
                      <Typography.Link href="/system-manager/channel" target="_blank" rel="noopener noreferrer">
                        {t('settings.assignStrategy.configureChannels')}
                      </Typography.Link>
                      <Button size="small" onClick={fetchChannelList}>{t('settings.assignStrategy.retryChannels')}</Button>
                    </Space>
                  </div>
                }
              />
            )}
          </div>
        </Form.Item>
        {selectedChannelIds.length > 0 && (
          <div className="mb-6 rounded-lg border border-[var(--color-border-1)] bg-[var(--color-fill-1)] p-3">
            <Typography.Text strong>{t('settings.notificationTemplate.bindingTitle')}</Typography.Text>
            <div className="mb-3 mt-1 text-sm text-[var(--color-text-3)]">
              {t('settings.notificationTemplate.bindingSteps')}
            </div>
            <div className="flex flex-col gap-3">
              {selectedChannelIds.map((channelId) => {
                const channel = channelList.find((item) => item.id.toString() === channelId);
                if (!channel) return null;
                const channelConfig = getNotificationTemplateChannel(channel.channel_type);
                const options = templateOptions[channel.channel_type] || [];
                return (
                  <div key={channelId} className="rounded border border-[var(--color-border-1)] bg-[var(--color-bg-1)] p-3">
                    <Space size={8} className="mb-3">
                      <Typography.Text strong>{channel.name} [{channel.channel_type}]</Typography.Text>
                      {channelConfig && <Tag>{t(channelConfig.labelKey)}</Tag>}
                    </Space>
                    <div className="grid grid-cols-1 gap-x-3 md:grid-cols-2">
                      {([
                        ['default', 'settings.notificationTemplate.sceneDefault'],
                        ['reminder', 'settings.notificationTemplate.sceneReminder'],
                        ['escalation', 'settings.notificationTemplate.sceneEscalation'],
                        ['recovery', 'settings.notificationTemplate.sceneRecovery'],
                      ] as const).map(([scene, labelKey]) => (
                        <Form.Item key={scene} name={['notification_templates', channelId, scene]} label={t(labelKey)}>
                          <Select
                            allowClear
                            className="w-full"
                            loading={templateLoading}
                            placeholder={t('settings.notificationTemplate.defaultTemplate')}
                            options={options}
                          />
                        </Form.Item>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
        <Collapse
          defaultActiveKey={[]}
          ghost
          expandIcon={({ isActive }) => (
            <CaretRightOutlined
              rotate={isActive ? 90 : 0}
              className="text-base"
            />
          )}
          items={[
            {
              key: 'advanced',
              label: (
              <div className="flex items-center text-base font-bold">
                {t('alarmCommon.advanced')}
              </div>
              ),
              children: (
                <>
            <Form.Item
              name="config"
              initialValue={defaultEffectiveTime}
              label={t('settings.assignStrategy.effectiveTime')}
              rules={[{ required: true, message: t('common.selectTip') }]}
            >
              <EffectiveTime open={open} />
            </Form.Item>
            <Form.Item
              name="notification_scenario"
              label={t('settings.assignStrategy.notificationScenario')}
              initialValue={['assignment']}
              rules={[{ required: true, message: t('common.selectTip') }]}
            >
              <Checkbox.Group
                options={[
                  {
                    label: t('settings.assignStrategy.assignment'),
                    value: 'assignment',
                  },
                  {
                    label: t('settings.assignStrategy.recovery'),
                    value: 'recovery',
                  },
                ]}
              />
            </Form.Item>
            <Form.Item
              label={t('settings.assignStrategy.notificationFrequency')}
            >
              <div className="mt-[5px]">
                {t('settings.assignStrategy.frequencyMsg')}
              </div>
              <div className="flex flex-row align-center gap-1 mt-2">
                <span className="mt-[4px]">
                  {t('settings.assignStrategy.notRespondMsg')}
                </span>
                <div className="flex flex-col">
                  {levelList.map(({ level_display_name, level_id, icon }) => (
                    <div key={level_id} className="flex items-center mb-2">
                      <Tag color={levelMap[level_id]}>
                        <div className="flex items-center">
                          <LevelIcon icon={icon} className="mr-1 w-4 h-4" />
                          {level_display_name || '--'}
                        </div>
                      </Tag>
                      <span>{t('settings.assignStrategy.notifyEvery')}</span>
                      <Space.Compact className="ml-2">
                        <Form.Item
                          name={[
                            'notification_frequency',
                            level_id,
                            'interval_minutes',
                          ]}
                          initialValue={0}
                          noStyle
                        >
                        <InputNumber
                          className="w-[110px]"
                          min={0}
                        />
                        </Form.Item>
                        <span className="flex items-center rounded-r-md border border-l-0 border-[var(--color-border-2)] bg-[var(--color-fill-1)] px-3 text-[var(--color-text-2)]">
                          {t('settings.assignStrategy.frequencyUnit')}
                        </span>
                      </Space.Compact>
                    </div>
                  ))}
                </div>
              </div>
            </Form.Item>
            <EscalationChain
              enabled={!!escalationEnabled}
              personnelOptions={personnelOptions}
              channelOptions={channelCheckOptions}
            />
                </>
              ),
            },
          ]}
        />
      </Form>
      </Drawer>
    </>
  );
};

export default OperateModalPage;
