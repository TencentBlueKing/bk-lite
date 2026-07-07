import React from 'react';
import { Button, Form, Input, message } from 'antd';
import { CopyOutlined } from '@ant-design/icons';
import type { EnterpriseWechatAibotNodeConfigProps } from './types';

export const EnterpriseWechatAibotNodeConfig: React.FC<EnterpriseWechatAibotNodeConfigProps> = ({ t, botId }) => {
  const callbackPath = `/api/v1/opspilot/bot_mgmt/execute_chat_flow_enterprise_wechat_aibot/${botId}/`;
  const callbackUrl = `${typeof window !== 'undefined' ? window.location.origin : ''}${callbackPath}`;

  const copyCallbackUrl = async () => {
    try {
      await navigator.clipboard.writeText(callbackUrl);
      message.success(t('chatflow.nodeConfig.apiLinkCopied'));
    } catch {
      const textArea = document.createElement('textarea');
      textArea.value = callbackUrl;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
      message.success(t('chatflow.nodeConfig.apiLinkCopied'));
    }
  };

  return (
    <div className="p-4 bg-[var(--color-fill-1)] border border-[var(--color-border-2)] rounded-md">
      <h4 className="text-sm font-medium mb-3">{t('chatflow.nodeConfig.enterpriseWechatAibotParams')}</h4>
      <Form.Item name="connectionMode" initialValue="webhook" hidden>
        <Input />
      </Form.Item>
      <Form.Item name={['websocket', 'botId']} initialValue="" hidden>
        <Input />
      </Form.Item>
      <Form.Item name={['websocket', 'secret']} initialValue="" hidden>
        <Input />
      </Form.Item>
      <Form.Item label={t('chatflow.nodeConfig.callbackUrl')}>
        <Input
          readOnly
          value={callbackUrl}
          addonAfter={<Button type="text" size="small" icon={<CopyOutlined />} onClick={copyCallbackUrl} />}
        />
      </Form.Item>
      <Form.Item
        label="Token"
        name={['webhook', 'token']}
        rules={[{ required: true, message: t('chatflow.nodeConfig.enterToken'), whitespace: true }]}
      >
        <Input.Password autoComplete="new-password" />
      </Form.Item>
      <Form.Item
        label="EncodingAESKey"
        name={['webhook', 'encodingAESKey']}
        rules={[{ required: true, message: t('chatflow.nodeConfig.enterEncodingAESKey'), whitespace: true }]}
      >
        <Input.Password autoComplete="new-password" />
      </Form.Item>
    </div>
  );
};
