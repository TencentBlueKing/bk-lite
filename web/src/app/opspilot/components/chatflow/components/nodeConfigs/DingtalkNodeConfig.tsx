import React from 'react';
import { Form, Input } from 'antd';
import type { DingtalkNodeConfigProps } from './types';

export const DingtalkNodeConfig: React.FC<DingtalkNodeConfigProps> = ({ t }) => {
  return (
    <div className="p-4 bg-[var(--color-fill-1)] border border-[var(--color-border-2)] rounded-md">
      <h4 className="text-sm font-medium mb-3">{t('chatflow.nodeConfig.dingtalkParams')}</h4>
      <div className="space-y-3">
        <Form.Item
          name="client_id"
          label="Client ID"
          rules={[{
            required: true,
            message: t('chatflow.nodeConfig.pleaseEnterClientId'),
            whitespace: true
          }]}
        >
          <Input placeholder={t('chatflow.nodeConfig.enterClientId')} />
        </Form.Item>
        <Form.Item
          name="client_secret"
          label="Client Secret"
          rules={[{
            required: true,
            message: t('chatflow.nodeConfig.pleaseEnterClientSecret'),
            whitespace: true
          }]}
          className="mb-0"
        >
          <Input.Password placeholder={t('chatflow.nodeConfig.enterClientSecret')} />
        </Form.Item>
      </div>
    </div>
  );
};
