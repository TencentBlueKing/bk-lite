'use client';

import React, { useState } from 'react';
import { Input, Button, message } from 'antd';
import { EyeOutlined, UpOutlined, DownOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';

interface CronEditorProps {
  value?: string;
  onChange?: (value: string) => void;
  disabled?: boolean;
}

interface CronParts {
  minute: string;
  hour: string;
  day: string;
  month: string;
  weekday: string;
}

const CronEditor: React.FC<CronEditorProps> = ({
  value = '* * * * *',
  onChange,
  disabled = false,
}) => {
  const { t } = useTranslation();
  const { post } = useApiClient();
  const [expanded, setExpanded] = useState(false);
  const [nextRuns, setNextRuns] = useState<string[]>([]);
  const [hasPreview, setHasPreview] = useState(false);
  const [loading, setLoading] = useState(false);

  // 解析 cron 表达式
  const parseCronParts = (cronValue: string): CronParts => {
    const parts = cronValue.split(' ');
    return {
      minute: parts[0] || '*',
      hour: parts[1] || '*',
      day: parts[2] || '*',
      month: parts[3] || '*',
      weekday: parts[4] || '*',
    };
  };

  const cronParts = parseCronParts(value);

  // 更新 cron 部分
  const updatePart = (part: keyof CronParts, newValue: string) => {
    const newParts = { ...cronParts, [part]: newValue || '*' };
    const newCron = `${newParts.minute} ${newParts.hour} ${newParts.day} ${newParts.month} ${newParts.weekday}`;
    onChange?.(newCron);
    // 清除预览结果，需要重新预览
    setHasPreview(false);
    setNextRuns([]);
  };

  // 预览按钮点击 - 调用后端接口
  const handlePreview = async () => {
    setLoading(true);
    try {
      const data = await post('/opspilot/bot_mgmt/bot/preview_crontab/', {
        crontab_expression: value,
      });
      if (Array.isArray(data)) {
        setNextRuns(data);
      } else {
        setNextRuns([]);
      }
      setHasPreview(true);
    } catch (error) {
      console.error('Preview cron failed:', error);
      message.error(t('common.fetchFailed'));
      setNextRuns([]);
    } finally {
      setLoading(false);
    }
  };

  const fields = [
    { key: 'minute' as const, label: t('chatflow.nodeConfig.cronMinute') },
    { key: 'hour' as const, label: t('chatflow.nodeConfig.cronHour') },
    { key: 'day' as const, label: t('chatflow.nodeConfig.cronDay') },
    { key: 'month' as const, label: t('chatflow.nodeConfig.cronMonth') },
    { key: 'weekday' as const, label: t('chatflow.nodeConfig.cronWeekday') },
  ];

  return (
    <div className="border border-gray-200 rounded-lg">
      {/* Cron 表达式标题栏 */}
      <div className="flex items-center justify-between px-4 py-3 bg-[var(--color-fill-1)]">
        <span className="font-medium text-sm">{t('chatflow.nodeConfig.cronExpression')}</span>
        <Button
          type="link"
          size="small"
          icon={<EyeOutlined />}
          onClick={handlePreview}
          loading={loading}
          disabled={disabled}
          className="text-[var(--color-primary)] p-0"
        >
          {t('chatflow.nodeConfig.previewSchedule')}
        </Button>
      </div>

      <div className="p-4">
        {/* 5字段输入 */}
        <div className="flex items-center gap-2">
          {fields.map((field, index) => (
            <React.Fragment key={field.key}>
              <div className="flex flex-col items-center">
                <span className="text-xs text-gray-500 mb-1">{field.label}</span>
                <Input
                  value={cronParts[field.key]}
                  onChange={(e) => updatePart(field.key, e.target.value)}
                  className="w-16 text-center"
                  disabled={disabled}
                />
              </div>
              {index < fields.length - 1 && (
                <span className="text-gray-400 mt-5">*</span>
              )}
            </React.Fragment>
          ))}
        </div>

        {/* 预览结果面板 */}
        {hasPreview && (
          <div className="mt-4 bg-gray-50 rounded-lg p-4">
            {nextRuns.length > 0 ? (
              <>
                {/* 下次执行时间 */}
                <div className="text-center mb-2">
                  <div className="text-sm text-gray-600">
                    {t('chatflow.nodeConfig.nextRun')}: <span className="font-medium text-gray-800">{nextRuns[0]}</span>
                    {nextRuns.length > 1 && (
                      <span
                        className="ml-2 cursor-pointer text-gray-400 hover:text-gray-600 inline-flex items-center"
                        onClick={() => setExpanded(!expanded)}
                      >
                        {expanded ? <UpOutlined /> : <DownOutlined />}
                      </span>
                    )}
                  </div>
                </div>

                {/* 展开显示更多执行时间 */}
                {expanded && nextRuns.length > 1 && (
                  <div className="border-t border-gray-200 pt-3 mt-3">
                    <div className="text-center text-sm text-gray-500 mb-2">
                      {t('chatflow.nodeConfig.upcomingRuns')}
                    </div>
                    <div className="space-y-1 text-center text-sm text-gray-600">
                      {nextRuns.slice(1).map((run, index) => (
                        <div key={index}>{run}</div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="text-center text-sm text-gray-400">
                {t('common.noData')}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default CronEditor;
