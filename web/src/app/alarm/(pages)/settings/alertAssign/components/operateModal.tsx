'use client';

import React, { useEffect, useState } from 'react';
import './operateModal.scss';
import MatchRule from '@/app/alarm/(pages)/settings/components/matchRule';
import EffectiveTime, {
  defaultEffectiveTime,
} from '@/app/alarm/(pages)/settings/components/effectiveTime';
import Icon from '@/components/icon';
import { useCommon } from '@/app/alarm/context/common';
import { useTranslation } from '@/utils/i18n';
import { CaretRightOutlined } from '@ant-design/icons';
import { useSettingApi } from '@/app/alarm/api/settings';
import { ChannelItem, NotifyOption } from '@/app/alarm/types/settings';
import {
  Tag,
  Form,
  Input,
  Select,
  Checkbox,
  Button,
  Drawer,
  Radio,
  Collapse,
  InputNumber,
  message,
  Spin,
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
  const locale = localStorage.getItem('locale') || 'en';
  const { t } = useTranslation();
  const { levelList, levelMap, userList } = useCommon();
  const { createAssignment, updateAssignment, getChannelList } =
    useSettingApi();

  const personnelOptions = userList.map(({ display_name, username }) => ({
    label: `${display_name} (${username})`,
    value: username,
  }));

  const [form] = Form.useForm();
  const [submitLoading, setSubmitLoading] = useState(false);
  const [notifyOptions, setNotifyOptions] = useState<NotifyOption[]>([]);
  const [channelList, setChannelList] = useState<ChannelItem[]>([]);
  const [channelLoading, setChannelLoading] = useState(false);

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

      if (!currentRow && data.length > 0) {
        form.setFieldsValue({
          notify_channels: [data[0].id.toString()],
        });
      }
    } catch (error) {
      console.error('获取通知渠道失败:', error);
    } finally {
      setChannelLoading(false);
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

        form.setFieldsValue({
          ...currentRow,
          notify_channels: notifyChannelIds,
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
        });
      } else {
        form.resetFields();
        form.setFieldsValue({ config: defaultEffectiveTime });
      }
    }
  }, [open, currentRow, form]);

  const ruleType = Form.useWatch('match_type', form);

  const onFinish = async (values: any) => {
    setSubmitLoading(true);
    try {
      const params = getParams(values);
      if (currentRow?.id) {
        await updateAssignment(currentRow.id, params);
      } else {
        await createAssignment(params);
      }
      message.success(
        currentRow ? t('alarmCommon.successOperate') : t('common.addSuccess')
      );
      form.resetFields();
      onClose();
      onSuccess && onSuccess();
    } catch {
      message.error(t('alarmCommon.operateFailed'));
    } finally {
      setSubmitLoading(false);
    }
  };

  const getParams = (values: any) => {
    const notifyChannels = (values.notify_channels || [])
      .map((id: string) => channelList.find((ch) => ch.id.toString() === id))
      .filter(Boolean);

    const params: any = {
      name: values.name,
      match_type: values.match_type,
      notify_channels: notifyChannels,
      personnel: values.personnel,
      config: values.config || defaultEffectiveTime,
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
    return params;
  };

  return (
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
        layout="horizontal"
        labelCol={{ span: locale === 'en' ? 5 : 4 }}
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
            style={{
              marginLeft: '110px',
              marginTop: '-10px',
              marginBottom: '26px',
            }}
            rules={[
              {
                validator: (_, value: any[][]) => {
                  if (!Array.isArray(value) || value.length === 0) {
                    return Promise.reject(new Error(t('common.inputTip')));
                  }
                  for (const orGroup of value) {
                    if (!Array.isArray(orGroup) || orGroup.length === 0) {
                      return Promise.reject(new Error(t('common.inputTip')));
                    }
                    for (const item of orGroup) {
                      if (
                        !item.key ||
                        !item.operator ||
                        (!item.value && item.value !== 0)
                      ) {
                        return Promise.reject(new Error(t('common.inputTip')));
                      }
                    }
                  }
                  return Promise.resolve();
                },
              },
            ]}
          >
            <MatchRule />
          </Form.Item>
        )}

        <Form.Item
          name="personnel"
          label={t('settings.assignStrategy.formPersonnelSelect')}
          rules={[
            {
              required: true,
              message: t('common.selectTip'),
            },
          ]}
        >
          <Select
            mode="multiple"
            options={personnelOptions}
            placeholder={`${t('common.selectTip')}`}
            filterOption={(input, option) =>
              (option?.label as string)
                ?.toLowerCase()
                .includes(input.toLowerCase())
            }
          />
        </Form.Item>
        <Form.Item
          name="notify_channels"
          label={t('settings.assignStrategy.formNotifyMethod')}
          rules={[{ required: true, message: t('common.selectTip') }]}
        >
          <Checkbox.Group options={notifyOptions} disabled={channelLoading} />
          {channelLoading && (
            <div className="flex justify-center h-[32px] ">
              <Spin spinning={channelLoading}></Spin>
            </div>
          )}
        </Form.Item>
        <Collapse
          defaultActiveKey={[]}
          ghost
          expandIcon={({ isActive }) => (
            <CaretRightOutlined
              rotate={isActive ? 90 : 0}
              className="text-base"
            />
          )}
        >
          <Collapse.Panel
            header={
              <div className="flex items-center text-base font-bold">
                {t('alarmCommon.advanced')}
              </div>
            }
            key="advanced"
          >
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
              name="notification_frequency"
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
                          <Icon type={icon} className="mr-1" />
                          {level_display_name || '--'}
                        </div>
                      </Tag>
                      <span>{t('settings.assignStrategy.notifyEvery')}</span>
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
                          className="ml-2 w-[150px]"
                          min={0}
                          addonAfter={t(
                            'settings.assignStrategy.frequencyUnit'
                          )}
                        />
                      </Form.Item>
                    </div>
                  ))}
                </div>
              </div>
            </Form.Item>
          </Collapse.Panel>
        </Collapse>
      </Form>
    </Drawer>
  );
};

export default OperateModalPage;
