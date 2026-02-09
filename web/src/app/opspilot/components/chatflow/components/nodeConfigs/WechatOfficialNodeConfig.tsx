import React from 'react';
import { Form, Input } from 'antd';
import type { WechatOfficialNodeConfigProps } from './types';

const FIELDS = ['token', 'appid', 'secret', 'aes_key'] as const;

export const WechatOfficialNodeConfig: React.FC<WechatOfficialNodeConfigProps> = ({ t }) => {
  return (
    <div className="p-4 bg-[var(--color-fill-1)] border border-[var(--color-border-2)] rounded-md">
      <h4 className="text-sm font-medium mb-3">{t('chatflow.nodeConfig.wechatOfficialParams')}</h4>
      <div className="space-y-3">
        {FIELDS.map((field, idx) => (
          <Form.Item
            key={field}
            name={field}
            label={field.toUpperCase().replace('_', ' ')}
            rules={[{
              required: true,
              message: `请输入${field.toUpperCase().replace('_', ' ')}`,
              whitespace: true
            }]}
            className={idx === FIELDS.length - 1 ? 'mb-0' : 'mb-3'}
          >
            {field.includes('secret') || field === 'aes_key' ?
              <Input.Password placeholder={`请输入${field.toUpperCase().replace('_', ' ')}`} /> :
              <Input placeholder={`请输入${field.toUpperCase().replace('_', ' ')}`} />
            }
          </Form.Item>
        ))}
      </div>
    </div>
  );
};
