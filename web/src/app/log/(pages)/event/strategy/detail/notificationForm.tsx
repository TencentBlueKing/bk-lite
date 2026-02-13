import React, { useMemo } from 'react';
import { Form, Switch, Button, Select } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { StrategyFields, ChannelItem, CardItem } from '@/app/log/types/event';
import { UserItem } from '@/app/log/types';
import SelectCard from './selectCard';

const { Option } = Select;

const getChannelIcon = (channelType: string): string => {
  const iconMap: Record<string, string> = {
    email: 'youjian',
    enterprise_wechat_bot: 'qiwei2',
    nats: 'dongzuo1'
  };
  return iconMap[channelType] || 'jiqiren3';
};

// 根据 channel_type 返回对应的翻译键
const getChannelTypeKey = (channelType: string): string => {
  const keyMap: Record<string, string> = {
    email: 'log.event.channelTypeEmail',
    enterprise_wechat_bot: 'log.event.channelTypeWechatBot',
    nats: 'log.event.channelTypeNats'
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

  // 通知渠道变更时清空通知者
  const handleChannelChange = () => {
    form.setFieldValue('notice_users', []);
  };

  // 将 channelList 转换为 SelectCard 需要的数据格式
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
          <span className="w-[100px]">{t('log.event.notificationConfig')}</span>
        }
      >
        <Form.Item name="notice" noStyle>
          <Switch />
        </Form.Item>
        <div className="text-[var(--color-text-3)] mt-[10px]">
          {t('log.event.notificationDesc')}
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
                    {t('log.event.notificationChannel')}
                  </span>
                }
                name="notice_type_id"
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
                    style={{ maxWidth: 800 }}
                    onChange={(val) => {
                      form.setFieldValue('notice_type_id', val);
                      handleChannelChange();
                    }}
                  />
                ) : (
                  <span>
                    {t('log.event.noticeWay')}
                    <Button
                      type="link"
                      className="p-0 mx-[4px]"
                      onClick={onLinkToSystemManage}
                    >
                      {t('log.event.systemManage')}
                    </Button>
                    {t('log.event.config')}
                  </span>
                )}
              </Form.Item>
              <Form.Item
                noStyle
                shouldUpdate={(prevValues, currentValues) =>
                  prevValues.notice_type_id !== currentValues.notice_type_id
                }
              >
                {({ getFieldValue }) =>
                  channelList.find(
                    (item) => item.id === getFieldValue('notice_type_id')
                  )?.channel_type === 'email' ? (
                    <Form.Item<StrategyFields>
                      label={
                        <span className="w-[100px]">
                          {t('log.event.notifier')}
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
                        style={{
                          width: '800px'
                        }}
                        showSearch
                        allowClear
                        mode="multiple"
                        maxTagCount="responsive"
                        placeholder={t('log.event.notifier')}
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
                    ) : (
                    <Form.Item<StrategyFields>
                      label={
                        <span className="w-[100px]">
                          {t('log.event.notifier')}
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
                        style={{
                          width: '800px'
                        }}
                        mode="tags"
                        placeholder={t('log.event.notifierTagsPlaceholder')}
                        suffixIcon={null}
                        open={false}
                      />
                    </Form.Item>
                    )
                }
              </Form.Item>
            </>
          ) : null
        }
      </Form.Item>
    </>
  );
};

export default NotificationForm;
