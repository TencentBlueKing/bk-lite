import React, { useMemo } from 'react';
import { Form, Switch, Button, Select } from 'antd';
import { useTranslation } from '@/utils/i18n';
import {
  StrategyFields,
  ChannelItem,
  CardItem
} from '@/app/monitor/types/event';
import { UserItem } from '@/app/monitor/types';
import SelectCard from './selectCard';

const { Option } = Select;

const getChannelIcon = (channelType: string): string => {
  const iconMap: Record<string, string> = {
    email: 'youjian',
    enterprise_wechat_bot: 'qiwei2',
    feishu_bot: 'feishu',
    dingtalk_bot: 'dingding',
    custom_webhook: 'webhook',
    nats: 'dongzuo1'
  };
  return iconMap[channelType] || 'jiqiren3';
};

const getChannelTypeKey = (channelType: string): string => {
  const keyMap: Record<string, string> = {
    email: 'monitor.events.channelTypeEmail',
    enterprise_wechat_bot: 'monitor.events.channelTypeWechatBot',
    feishu_bot: 'monitor.events.channelTypeFeishuBot',
    dingtalk_bot: 'monitor.events.channelTypeDingtalkBot',
    custom_webhook: 'monitor.events.channelTypeCustomWebhook',
    nats: 'monitor.events.channelTypeNats'
  };
  return keyMap[channelType] || '';
};

interface NotificationFormProps {
  channelList: ChannelItem[];
  userList: UserItem[];
  onLinkToSystemManage: () => void;
}

const NotificationForm: React.FC<NotificationFormProps> = ({
  channelList,
  userList,
  onLinkToSystemManage
}) => {
  const { t } = useTranslation();
  const form = Form.useFormInstance<StrategyFields>();

  const handleChannelChange = (newIds: (string | number)[]) => {
    form.setFieldValue('notice_type_ids', newIds);
    const selectedTypes = channelList
      .filter((ch) => newIds.includes(ch.id))
      .map((ch) => ch.channel_type);
    const allNats = selectedTypes.length > 0 && selectedTypes.every((t) => t === 'nats');
    if (allNats) {
      form.setFieldValue('notice_users', []);
    }
  };

  const channelCardData: CardItem[] = useMemo(() => {
    return channelList.map((item) => {
      const tagKey = getChannelTypeKey(item.channel_type);
      return {
        icon: getChannelIcon(item.channel_type),
        title: item.name,
        tag: tagKey ? t(tagKey) : item.channel_type,
        description: item.description,
        value: item.id
      };
    });
  }, [channelList, t]);

  return (
    <>
      <Form.Item<StrategyFields>
        label={
          <span className="w-[100px]">
            {t('monitor.events.notificationConfig')}
          </span>
        }
      >
        <Form.Item name="notice" noStyle>
          <Switch />
        </Form.Item>
        <div className="text-[var(--color-text-3)] mt-[10px]">
          {t('monitor.events.notificationDesc')}
        </div>
      </Form.Item>
      <Form.Item
        noStyle
        shouldUpdate={(prevValues, currentValues) =>
          prevValues.notice !== currentValues.notice
        }
      >
        {({ getFieldValue }) =>
          getFieldValue('notice') ? (
            <>
              <Form.Item<StrategyFields>
                label={
                  <span className="w-[100px]">
                    {t('monitor.events.notificationChannel')}
                  </span>
                }
                name="notice_type_ids"
                rules={[
                  {
                    required: true,
                    message: t('common.required')
                  }
                ]}
              >
                {channelList.length ? (
                  <SelectCard
                    data={channelCardData}
                    onChange={handleChannelChange}
                  />
                ) : (
                  <span>
                    {t('monitor.events.noticeWay')}
                    <Button
                      type="link"
                      className="p-0 mx-[4px]"
                      onClick={onLinkToSystemManage}
                    >
                      {t('monitor.events.systemManage')}
                    </Button>
                    {t('monitor.events.config')}
                  </span>
                )}
              </Form.Item>
              <Form.Item
                noStyle
                shouldUpdate={(prevValues, currentValues) =>
                  prevValues.notice_type_ids !== currentValues.notice_type_ids
                }
              >
                {({ getFieldValue }) => {
                  const selectedIds: number[] = getFieldValue('notice_type_ids') || [];
                  const selectedChannels = channelList.filter((item) => selectedIds.includes(item.id));
                  const channelTypes = selectedChannels.map((ch) => ch.channel_type);

                  if (!selectedChannels.length || channelTypes.every((t) => t === 'nats')) {
                    return null;
                  }

                  const hasEmail = channelTypes.includes('email');

                  if (hasEmail) {
                    return (
                      <Form.Item<StrategyFields>
                        label={
                          <span className="w-[100px]">
                            {t('monitor.events.notifier')}
                          </span>
                        }
                        name="notice_users"
                        rules={[
                          {
                            required: true,
                            message: t('common.required')
                          }
                        ]}
                      >
                        <Select
                          style={{ width: '100%' }}
                          showSearch
                          allowClear
                          mode="multiple"
                          maxTagCount="responsive"
                          placeholder={t('monitor.events.notifier')}
                          virtual
                          filterOption={(input, option) => {
                            const user = userList.find(
                              (u) => u.id === option?.value
                            );
                            if (!user) return false;
                            const searchText = input.toLowerCase();
                            return (
                              user.display_name?.toLowerCase() || ''
                            ).includes(searchText);
                          }}
                          optionLabelProp="label"
                        >
                          {userList.map((item) => (
                            <Option
                              value={item.id}
                              key={item.id}
                              label={item.display_name}
                            >
                              {item.display_name}
                            </Option>
                          ))}
                        </Select>
                      </Form.Item>
                    );
                  }

                  return (
                    <Form.Item<StrategyFields>
                      label={
                        <span className="w-[100px]">
                          {t('monitor.events.notifier')}
                        </span>
                      }
                      name="notice_users"
                      rules={[
                        {
                          required: true,
                          message: t('common.required')
                        }
                      ]}
                    >
                      <Select
                        style={{ width: '100%' }}
                        mode="tags"
                        placeholder={t(
                          'monitor.events.notifierTagsPlaceholder'
                        )}
                        suffixIcon={null}
                        open={false}
                      />
                    </Form.Item>
                  );
                }}
              </Form.Item>
            </>
          ) : null
        }
      </Form.Item>
    </>
  );
};

export default NotificationForm;
