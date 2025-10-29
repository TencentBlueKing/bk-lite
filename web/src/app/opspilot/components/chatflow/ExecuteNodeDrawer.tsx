'use client';

import React from 'react';
import { Drawer, Form, Input, Button, Spin, Typography } from 'antd';
import { useTranslation } from '@/utils/i18n';

const { TextArea } = Input;
const { Text } = Typography;

interface ExecuteNodeDrawerProps {
  visible: boolean;
  nodeId: string;
  message: string;
  result: any;
  loading: boolean;
  onMessageChange: (message: string) => void;
  onExecute: () => void;
  onClose: () => void;
}

const ExecuteNodeDrawer: React.FC<ExecuteNodeDrawerProps> = ({
  visible,
  nodeId,
  message,
  result,
  loading,
  onMessageChange,
  onExecute,
  onClose
}) => {
  const { t } = useTranslation();

  const renderResult = () => {
    if (!result) return null;

    return (
      <div className="mt-4">
        <h3 className="mb-2">{t('chatflow.executeResult')}</h3>
        <div className="bg-gray-50 p-4 rounded-md border">
          <pre className="whitespace-pre-wrap text-sm overflow-auto max-h-60">
            {JSON.stringify(result?.content, null, 2)}
          </pre>
        </div>
      </div>
    );
  };

  return (
    <Drawer
      title={t('chatflow.executeNode')}
      open={visible}
      onClose={onClose}
      width={480}
      placement="right"
      footer={
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button 
            type="primary" 
            onClick={onExecute}
            loading={loading}
          >
            {t('common.execute')}
          </Button>
        </div>
      }
    >
      <div>
        <div className="mb-4">
          <Text type="secondary">
            {t('chatflow.nodeConfig.nodeName')}: {nodeId}
          </Text>
        </div>

        <Form layout="vertical">
          <Form.Item 
            label={t('chatflow.executeMessage')}
          >
            <TextArea
              rows={4}
              value={message}
              onChange={(e) => onMessageChange(e.target.value)}
              placeholder={t('chatflow.executeMessagePlaceholder')}
            />
          </Form.Item>
        </Form>

        {loading && (
          <div className="text-center my-4">
            <Spin size="large" />
          </div>
        )}

        {renderResult()}
      </div>
    </Drawer>
  );
};

export default ExecuteNodeDrawer;