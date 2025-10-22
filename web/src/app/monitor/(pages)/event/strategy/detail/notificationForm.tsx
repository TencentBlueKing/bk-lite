import React from 'react';
import { Form, Switch, Button, Radio, Select, Input } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { StrategyFields, ChannelItem } from '@/app/monitor/types/event';
import { UserItem } from '@/app/monitor/types';

const { Option } = Select;

interface NotificationFormProps {
  channelList: ChannelItem[];
  userList: UserItem[];
  onLinkToSystemManage: () => void;
}

const NotificationForm: React.FC<NotificationFormProps> = ({
  channelList,
  userList,
  onLinkToSystemManage,
}) => {
  const { t } = useTranslation();

  return (
    <>
      <Form.Item<StrategyFields>
        label={
          <span className="w-[100px]">{t('monitor.events.notification')}</span>
        }
        name="notice"
      >
        <Switch />
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
                    {t('monitor.events.method')}
                  </span>
                }
                name="notice_type_id"
                rules={[
                  {
                    required: true,
                    message: t('common.required'),
                  },
                ]}
              >
                {channelList.length ? (
                  <Radio.Group>
                    {channelList.map((item) => (
                      <Radio key={item.id} value={item.id}>
                        {`${item.name}（${item.channel_type}）`}
                      </Radio>
                    ))}
                  </Radio.Group>
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
                            {t('monitor.events.notifier')}
                          </span>
                        }
                        name="notice_users"
                        rules={[
                          {
                            required: true,
                            message: t('common.required'),
                          },
                        ]}
                      >
                        <Select
                          style={{
                            width: '800px',
                          }}
                          showSearch
                          allowClear
                          mode="multiple"
                          maxTagCount="responsive"
                          placeholder={t('monitor.events.notifier')}
                        >
                          {userList.map((item) => (
                            <Option value={item.id} key={item.id}>
                              {item.username}
                            </Option>
                          ))}
                        </Select>
                      </Form.Item>
                    ) : (
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
                            message: t('common.required'),
                          },
                        ]}
                      >
                        <Input
                          style={{
                            width: '800px',
                          }}
                          placeholder={t('monitor.events.notifier')}
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
