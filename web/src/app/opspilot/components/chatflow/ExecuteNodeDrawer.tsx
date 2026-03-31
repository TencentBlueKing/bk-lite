'use client';

import React from 'react';
import { Drawer, Form, Input, Button, Typography } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { NodeExecutionResult } from './hooks/useNodeExecution';

const { TextArea } = Input;
const { Text } = Typography;

interface ExecuteNodeDrawerProps {
  visible: boolean;
  nodeId: string;
  message: string;
  result: NodeExecutionResult | null;
  loading: boolean;
  streamingContent: string;
  onMessageChange: (message: string) => void;
  onExecute: () => void;
  onClose: () => void;
  onStop?: () => void;
}

const ExecuteNodeDrawer: React.FC<ExecuteNodeDrawerProps> = ({
  visible,
  nodeId,
  message,
  result,
  loading,
  streamingContent,
  onMessageChange,
  onExecute,
  onClose,
  onStop
}) => {
  const { t } = useTranslation();

  return (
    <Drawer
      title={t('chatflow.executeNode')}
      open={visible}
      onClose={onClose}
      width={420}
      placement="right"
      footer={
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>
            {t('common.cancel')}
          </Button>
          {loading && onStop ? (
            <Button onClick={onStop} danger>
              {t('common.stop')}
            </Button>
          ) : (
            <Button
              type="primary"
              onClick={onExecute}
              loading={loading}
            >
              {t('common.execute')}
            </Button>
          )}
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
              disabled={loading}
            />
          </Form.Item>
        </Form>

        <div className="rounded-2xl border border-(--color-border-1) bg-(--color-fill-1) p-4 text-sm leading-6 text-(--color-text-3)">
          {loading
            ? t('chatflow.preview.executingHint')
            : (result?.error || result?.content || streamingContent)
              ? t('chatflow.preview.executionTransferred')
              : t('chatflow.preview.executeDrawerHint')}
        </div>
      </div>
    </Drawer>
  );
};

export default ExecuteNodeDrawer;
