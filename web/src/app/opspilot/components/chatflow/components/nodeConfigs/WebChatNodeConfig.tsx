import React from 'react';
import { Form, Input, Button } from 'antd';
import { ExportOutlined } from '@ant-design/icons';
import Icon from '@/components/icon';
import type { WebChatNodeConfigProps } from './types';

const { TextArea } = Input;

const ICON_TYPES = ['duihuazhinengti', 'a-zhinengti', 'zhinengtitubiao', 'zhinengti1', 'zhinengti2'];

export const WebChatNodeConfig: React.FC<WebChatNodeConfigProps> = ({
  t,
  form,
}) => {
  const webAccessUrl = `${typeof window !== 'undefined' ? window.location.origin : ''}/opspilot/studio/chat`;

  return (
    <>
      <Form.Item
        name="appName"
        label={t('chatflow.nodeConfig.appName')}
        rules={[{
          required: true,
          message: t('chatflow.nodeConfig.pleaseEnterAppName'),
          whitespace: true
        }]}
      >
        <Input placeholder={t('chatflow.nodeConfig.enterAppName')} />
      </Form.Item>
      <Form.Item
        name="appIcon"
        label={t('chatflow.nodeConfig.appIcon')}
        rules={[{
          required: true,
          message: t('chatflow.nodeConfig.pleaseSelectAppIcon')
        }]}
      >
        <Form.Item noStyle shouldUpdate={(prev, curr) => prev.appIcon !== curr.appIcon}>
          {() => (
            <div className="flex gap-3">
              {ICON_TYPES.map(iconType => (
                <div
                  key={iconType}
                  onClick={() => {
                    form.setFieldValue('appIcon', iconType);
                    form.validateFields(['appIcon']);
                  }}
                  className={`w-10 h-10 flex items-center justify-center rounded cursor-pointer transition-all ${
                    form.getFieldValue('appIcon') === iconType
                      ? 'border-2 border-blue-500 bg-blue-50/50'
                      : 'border border-gray-200 hover:border-gray-300'
                  }`}
                >
                  <Icon type={iconType} className="text-2xl" />
                </div>
              ))}
            </div>
          )}
        </Form.Item>
      </Form.Item>
      <Form.Item
        name="appDescription"
        label={t('chatflow.nodeConfig.appDescription')}
        rules={[{
          required: true,
          message: t('chatflow.nodeConfig.pleaseEnterAppDescription'),
          whitespace: true
        }]}
      >
        <TextArea
          rows={4}
          placeholder={t('chatflow.nodeConfig.enterAppDescription')}
        />
      </Form.Item>
      <div className="p-3 bg-blue-50 border border-blue-200 rounded-md text-xs">
        <div className="flex items-center justify-between mb-1">
          <p className="text-gray-600">
            {t('chatflow.nodeConfig.webAccessAddress')}：
          </p>
          <Button
            type="text"
            size="small"
            icon={<ExportOutlined />}
            className="text-gray-400 hover:text-gray-600"
            onClick={() => window.open(webAccessUrl, '_blank')}
          />
        </div>
        <div className="font-mono text-blue-600 break-all">
          {webAccessUrl}
        </div>
      </div>
    </>
  );
};
