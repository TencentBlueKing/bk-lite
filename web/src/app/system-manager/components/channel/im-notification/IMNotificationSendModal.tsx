import React from 'react';
import { Form, Input, Select } from 'antd';
import type { FormInstance } from 'antd';

import OperateModal from '@/components/operate-modal';

interface IMNotificationSendModalProps {
  open: boolean;
  loading: boolean;
  form: FormInstance;
  channelOptions: Array<{ value: number; label: string }>;
  receiverOptions: Array<{ value: number; label: string }>;
  receiversLoading: boolean;
  selectedChannelId: number | undefined;
  t: (key: string, defaultMessage?: string, values?: Record<string, string | number>) => string;
  onOk: () => void;
  onCancel: () => void;
  onChannelChange: (channelId: number) => void;
}

const IMNotificationSendModal: React.FC<IMNotificationSendModalProps> = ({
  open,
  loading,
  form,
  channelOptions,
  receiverOptions,
  receiversLoading,
  selectedChannelId,
  t,
  onOk,
  onCancel,
  onChannelChange,
}) => (
  <OperateModal
    title={t('system.channel.imNotificationPage.sendTitle')}
    open={open}
    onOk={onOk}
    onCancel={onCancel}
    confirmLoading={loading}
    width={520}
  >
    <Form form={form} layout="vertical">
      <Form.Item
        name="channel_id"
        label={t('system.channel.imNotificationPage.sendChannel')}
        rules={[{ required: true }]}
      >
        <Select
          placeholder={t('system.channel.imNotificationPage.sendChannelPlaceholder')}
          options={channelOptions}
          onChange={onChannelChange}
        />
      </Form.Item>
      <Form.Item
        name="user_ids"
        label={t('system.channel.imNotificationPage.sendReceivers')}
        rules={[{ required: true }]}
      >
        <Select
          mode="multiple"
          placeholder={t('system.channel.imNotificationPage.sendReceiversPlaceholder')}
          options={receiverOptions}
          loading={receiversLoading}
          disabled={!selectedChannelId}
        />
      </Form.Item>
      <Form.Item
        name="title"
        label={t('system.channel.imNotificationPage.sendMessageTitle')}
        rules={[{ required: true }]}
      >
        <Input />
      </Form.Item>
      <Form.Item
        name="content"
        label={t('system.channel.imNotificationPage.sendMessageContent')}
        rules={[{ required: true }]}
      >
        <Input.TextArea rows={4} />
      </Form.Item>
    </Form>
  </OperateModal>
);

export default IMNotificationSendModal;
