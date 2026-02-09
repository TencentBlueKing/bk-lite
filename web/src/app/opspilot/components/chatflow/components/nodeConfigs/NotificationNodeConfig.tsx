import React from 'react';
import { Form, Input, Select, Radio } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import Link from 'next/link';
import type { NotificationNodeConfigProps } from './types';

const { Option } = Select;
const { TextArea } = Input;

export const NotificationNodeConfig: React.FC<NotificationNodeConfigProps> = ({
  t,
  notificationType,
  setNotificationType,
  notificationChannels,
  loadingChannels,
  loadChannels,
  allUsers,
  loadingUsers,
  form,
}) => {
  return (
    <>
      <Form.Item name="notificationType" label={t('chatflow.notificationCategory')} initialValue="email" rules={[{ required: true }]}>
        <Radio.Group onChange={(e) => {
          setNotificationType(e.target.value);
          loadChannels(e.target.value);
          form.setFieldsValue({ notificationMethod: undefined });
        }}>
          <Radio value="email">{t('chatflow.email')}</Radio>
          <Radio value="enterprise_wechat_bot">{t('chatflow.enterpriseWechatBot')}</Radio>
        </Radio.Group>
      </Form.Item>
      <Form.Item name="notificationMethod" label={
        <div className="flex items-center justify-between" style={{ width: '600px' }}>
          <span>{t('chatflow.notificationMethod')}</span>
          <Link href="/system-manager/channel" target="_blank" className="text-blue-500 hover:text-blue-600 text-xs flex items-center gap-1 whitespace-nowrap">
            <PlusOutlined />
            {t('chatflow.addNotificationChannel')}
          </Link>
        </div>
      } rules={[{ required: true }]}>
        <Select placeholder={t('chatflow.selectNotificationMethod')} loading={loadingChannels}>
          {notificationChannels.map((c) => <Option key={c.id} value={c.id}>{c.name}</Option>)}
        </Select>
      </Form.Item>
      {notificationType === 'email' && (
        <>
          <Form.Item name="notificationRecipients" label={t('chatflow.notificationRecipients')} rules={[{ required: true }]}>
            <Select
              mode="multiple"
              placeholder={t('chatflow.selectNotificationRecipients')}
              loading={loadingUsers}
              showSearch
              filterOption={(input, option) => {
                const label = option?.label as string || '';
                return label.toLowerCase().includes(input.toLowerCase());
              }}
              optionFilterProp="label"
            >
              {allUsers.map((u) => <Option key={u.id} value={u.id} label={`${u.display_name || u.name}(${u.username})`}>{u.display_name || u.name}({u.username})</Option>)}
            </Select>
          </Form.Item>
          <Form.Item name="notificationTitle" label={t('chatflow.notificationTitle')} rules={[{ required: true }]}>
            <Input placeholder={t('chatflow.enterNotificationTitle')} />
          </Form.Item>
        </>
      )}
      <Form.Item name="notificationContent" label={t('chatflow.notificationContent')} rules={[{ required: true }]} initialValue="{{last_message}}">
        <TextArea rows={4} placeholder={t('chatflow.enterNotificationContent')} />
      </Form.Item>
    </>
  );
};
