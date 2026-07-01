'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Timeline, Button, Spin, Empty, message } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { useSettingApi } from '@/app/alarm/api/settings';
import { ACTION_EXEC_STATUS, ACTION_TRIGGER_EVENTS } from '@/app/alarm/constants/settings';
import { ActionExecutionItem } from '@/app/alarm/types/settings';

interface ActionTimelineProps {
  alertId: string;
}

const STATUS_COLOR_MAP: Record<string, string> = {
  success: 'green',
  failed: 'red',
  running: 'blue',
  pending: 'gray',
  skipped: 'gray',
  config_error: 'gray',
};

const ActionTimeline: React.FC<ActionTimelineProps> = ({ alertId }) => {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const { getActionExecutions, manualTriggerAction } = useSettingApi();
  const [loading, setLoading] = useState<boolean>(false);
  const [rerunLoadingId, setRerunLoadingId] = useState<number | null>(null);
  const [items, setItems] = useState<ActionExecutionItem[]>([]);

  const fetchData = useCallback(async () => {
    if (!alertId) return;
    setLoading(true);
    try {
      const data: any = await getActionExecutions({
        alert_id: alertId,
        page: 1,
        page_size: 100,
      });
      setItems(data?.items || []);
    } finally {
      setLoading(false);
    }
  }, [alertId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleRerun = async (item: ActionExecutionItem) => {
    if (!item.rule) return;
    setRerunLoadingId(item.id);
    try {
      await manualTriggerAction({ alert_id: alertId, rule_id: item.rule });
      message.success(t('common.operationSuccess') || '操作成功');
      await fetchData();
    } catch {
      message.error(t('common.operationFailed') || '操作失败');
    } finally {
      setRerunLoadingId(null);
    }
  };

  const getTriggerLabel = (item: ActionExecutionItem): string => {
    if (item.trigger_type === 'manual') {
      const base = '手动触发';
      return item.operator ? `${base} by ${item.operator}` : base;
    }
    return '自动触发';
  };

  const getTriggerEventLabel = (item: ActionExecutionItem): string => {
    if (item.trigger_type === 'manual') return '手动';
    const found = ACTION_TRIGGER_EVENTS.find((e) => e.value === item.trigger_event);
    return found ? found.label : item.trigger_event;
  };

  const timelineItems = items.map((item) => {
    const statusInfo = ACTION_EXEC_STATUS[item.status] || { text: item.status, color: 'default' };
    const dotColor = STATUS_COLOR_MAP[item.status] || 'gray';
    const isFailed = item.status === 'failed' || item.status === 'config_error';
    const errorMsg = isFailed && item.result?.message ? String(item.result.message) : null;

    return {
      color: dotColor,
      children: (
        <div className="text-sm pb-2">
          <div className="flex items-center gap-2 font-medium">
            <span>{item.rule_name || '动作'}</span>
            <span className="text-[var(--color-text-3)]">·</span>
            <span className="text-[var(--color-text-3)]">作业</span>
            <span
              className="ml-1 px-1.5 py-0.5 rounded text-xs"
              style={{
                color: dotColor === 'green' ? '#52c41a' : dotColor === 'red' ? '#ff4d4f' : dotColor === 'blue' ? '#1677ff' : '#8c8c8c',
                background: dotColor === 'green' ? '#f6ffed' : dotColor === 'red' ? '#fff2f0' : dotColor === 'blue' ? '#e6f4ff' : '#f5f5f5',
              }}
            >
              {statusInfo.text}
            </span>
          </div>
          <div className="text-[var(--color-text-3)] mt-0.5">
            {getTriggerLabel(item)}
            <span className="mx-1">·</span>
            {getTriggerEventLabel(item)}
            <span className="mx-1">·</span>
            {item.created_at ? convertToLocalizedTime(item.created_at) : '--'}
          </div>
          {item.job_detail_url && (
            <div className="mt-1">
              <a href={item.job_detail_url} target="_blank" rel="noopener noreferrer" className="text-[var(--color-primary)]">
                查看作业
              </a>
            </div>
          )}
          {isFailed && (
            <div className="mt-1 flex items-start gap-2">
              {errorMsg && (
                <span className="text-red-500 flex-1">{errorMsg}</span>
              )}
              <Button
                size="small"
                danger
                loading={rerunLoadingId === item.id}
                disabled={!item.rule}
                onClick={() => handleRerun(item)}
              >
                {t('settings.actionRerun')}
              </Button>
            </div>
          )}
        </div>
      ),
    };
  });

  return (
    <Spin spinning={loading}>
      {!loading && items.length === 0 ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={t('common.noData')}
        />
      ) : (
        <div className="pt-[10px]">
          <Timeline items={timelineItems} />
        </div>
      )}
    </Spin>
  );
};

export default ActionTimeline;
