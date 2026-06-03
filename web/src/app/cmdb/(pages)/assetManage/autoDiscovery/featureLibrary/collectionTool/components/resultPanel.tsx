'use client';

import React from 'react';
import { Button, Alert, Typography, Space } from 'antd';
import { DownloadOutlined } from '@ant-design/icons';
import type { CollectToolExecuteResponse, ExecStatus } from '@/app/cmdb/types/collectTool';
import { useTranslation } from '@/utils/i18n';

const { Text } = Typography;

interface ResultPanelProps {
  result: CollectToolExecuteResponse | null;
  execStatus: ExecStatus;
  timerDisplay: string;
  onReset?: () => void;
  isRunning?: boolean;
}

const ResultPanel: React.FC<ResultPanelProps> = ({
  result,
  execStatus,
  timerDisplay,
  onReset,
  isRunning,
}) => {
  const { t } = useTranslation();

  const handleExport = () => {
    if (!result?.raw_log) return;
    const protocol = result.protocol || 'unknown';
    const ip = result.meta?.target?.replace(/\./g, '-') || 'unknown';
    const now = new Date();
    const ts = [
      now.getFullYear(),
      String(now.getMonth() + 1).padStart(2, '0'),
      String(now.getDate()).padStart(2, '0'),
      String(now.getHours()).padStart(2, '0'),
      String(now.getMinutes()).padStart(2, '0'),
      String(now.getSeconds()).padStart(2, '0'),
    ].join('');
    const filename = `collection_log_${protocol}_${ip}_${ts}.txt`;
    const blob = new Blob([result.raw_log], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  const renderStatusBar = () => {
    if (execStatus === 'submitting' || execStatus === 'running') {
      return (
        <div className="flex items-center gap-3 mb-3 text-blue-600">
          <span className="animate-pulse">● Running</span>
          <span className="font-mono text-sm">Timer: {timerDisplay}</span>
        </div>
      );
    }
    if (execStatus === 'success') {
      return (
        <div className="flex items-center gap-2 mb-3 text-green-600">
          <span>✓ {t('CollectTool.success')}</span>
          {result && (
            <span className="text-gray-400 text-xs">
              {result.duration_ms}ms
            </span>
          )}
        </div>
      );
    }
    if (execStatus === 'error') {
      return (
        <div className="flex items-center gap-2 mb-3 text-red-600">
          <span>✗ {t('CollectTool.failed')}</span>
          {result && (
            <span className="text-gray-400 text-xs">
              {result.duration_ms}ms
            </span>
          )}
        </div>
      );
    }
    return null;
  };

  const hasRawLog = Boolean(result?.raw_log);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between mb-2">
        <Text strong>{t('CollectTool.resultTitle')}</Text>
        <Space>
          {onReset && (
            <Button size="small" onClick={onReset} disabled={!isRunning}>
              {t('CollectTool.pause')}
            </Button>
          )}
          <Button
            size="small"
            icon={<DownloadOutlined />}
            disabled={!hasRawLog}
            onClick={handleExport}
          >
            {t('CollectTool.exportText')}
          </Button>
        </Space>
      </div>

      {renderStatusBar()}

      {result?.summary && !result.success && (
        <Alert
          type="error"
          message={result.summary}
          className="mb-3"
          showIcon
        />
      )}

      <div
        className="flex-1 min-h-0 overflow-auto rounded bg-gray-900 p-3 font-mono text-xs text-green-400"
        style={{ minHeight: 200, whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}
      >
        {hasRawLog ? result!.raw_log : (
          <span className="text-gray-500 italic">
            {execStatus === 'idle' ? t('CollectTool.noResult') : ''}
          </span>
        )}
      </div>
    </div>
  );
};

export default ResultPanel;
