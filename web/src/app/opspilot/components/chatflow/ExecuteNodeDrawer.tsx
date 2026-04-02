'use client';

import React from 'react';
import { Alert, Button, Drawer, Form, Input, Typography } from 'antd';
import { useTranslation } from '@/utils/i18n';

const { TextArea } = Input;
const { Text } = Typography;

interface ExecuteNodeDrawerProps {
  visible: boolean;
  nodeName: string;
  message: string;
  loading: boolean;
  onMessageChange: (message: string) => void;
  onExecute: () => void;
  onClose: () => void;
  onStop?: () => void;
}

const ExecuteNodeDrawer: React.FC<ExecuteNodeDrawerProps> = ({
  visible,
  nodeName,
  message,
  loading,
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
            {t('chatflow.nodeConfig.nodeName')}: {nodeName}
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

        <Alert
          showIcon
          type={loading ? 'success' : 'info'}
          message={
            <span className="text-xs leading-5">
              {loading ? t('chatflow.preview.executingHint') : t('chatflow.preview.executeDrawerHint')}
            </span>
          }
        />
      </div>
    </Drawer>
  );
};

export default ExecuteNodeDrawer;
