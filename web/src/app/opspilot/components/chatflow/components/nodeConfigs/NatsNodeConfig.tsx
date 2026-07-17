import React from 'react';
import { Form, Input, Switch } from 'antd';
import { useTranslation } from '@/utils/i18n';

const { TextArea } = Input;

export const NatsNodeConfig: React.FC = () => {
  const { t } = useTranslation();
  return (
    <>
      <Form.Item name="appName" label={t('chatflow.nodeConfig.appName')}>
        <Input placeholder={t('chatflow.nodeConfig.natsOptionalAppName')} />
      </Form.Item>
      <Form.Item name="appDescription" label={t('chatflow.nodeConfig.appDescription')}>
        <TextArea rows={3} placeholder={t('chatflow.nodeConfig.natsOptionalAppDescription')} />
      </Form.Item>
      <Form.Item
        name="exposeAsWebChat"
        label={t('chatflow.nodeConfig.exposeAsWebChat')}
        valuePropName="checked"
        tooltip={t('chatflow.nodeConfig.exposeAsWebChatTooltip')}
      >
        <Switch />
      </Form.Item>
    </>
  );
};
