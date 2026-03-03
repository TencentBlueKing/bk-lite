import React from 'react';
import { Input, Button } from 'antd';
import { CopyOutlined } from '@ant-design/icons';
import Link from 'next/link';
import type { ApiInfoNodeConfigProps } from './types';

export const ApiInfoNodeConfig: React.FC<ApiInfoNodeConfigProps> = ({
  t,
  nodeType,
  botId,
  nodeId,
  copyApiUrl,
}) => {
  const apiUrl = `${typeof window !== 'undefined' ? window.location.origin : ''}/api/v1/opspilot/bot_mgmt/execute_chat_flow/${botId}/${nodeId}`;
  const infoKey = nodeType === 'embedded_chat' ? 'agui' : nodeType;

  return (
    <div className="p-4 bg-blue-50 border border-blue-200 rounded-md text-xs leading-5">
      <p className="text-gray-500 mb-2">{t(`chatflow.nodeConfig.${infoKey}ApiInfo`)}</p>
      <div className="mt-2 mb-2 relative">
        <Input.TextArea
          readOnly
          value={apiUrl}
          autoSize={{ minRows: 2, maxRows: 4 }}
          className="font-mono text-xs text-gray-700 bg-white pr-10 border-none"
        />
        <Button type="text" icon={<CopyOutlined />} size="small" onClick={copyApiUrl} className="absolute top-2 right-2" />
      </div>
      <span className="text-gray-500">{t('chatflow.nodeConfig.moreDetails')}</span>
      <Link href="/opspilot/studio/detail/api" target="_blank" className="text-blue-500 hover:underline">
        {t('chatflow.nodeConfig.viewApiDocs')}
      </Link>
    </div>
  );
};
