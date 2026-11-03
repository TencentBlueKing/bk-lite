'use client';

import { Alert } from 'antd';

import { useTranslation } from '@/utils/i18n';
import { summarizeTerminationJobCancels } from '../lib/presentation';
import type { ExecutionRecord } from '../lib/types';

interface ExecutionTerminationResidualAlertProps {
  execution: ExecutionRecord;
}

export function ExecutionTerminationResidualAlert({ execution }: ExecutionTerminationResidualAlertProps) {
  const { t } = useTranslation();
  const isTerminatingFlow = execution.status === 'TERMINATING' || execution.status === 'TERMINATED';
  if (!isTerminatingFlow) return null;

  const summary = summarizeTerminationJobCancels(execution.output);
  if (!summary) return null;

  if (summary.hasResidual) {
    return (
      <Alert
        className="mt-3"
        type="warning"
        showIcon
        data-testid="execution-termination-residual-alert"
        message={t(
          'workflowOrchestration.execution.terminationResidualTitle',
          '仍有 {failed} 个关联作业未能确认停止，目标主机上可能仍有任务在执行',
          { failed: summary.failed },
        )}
        description={(
          <div className="flex flex-col gap-1">
            <p className="m-0 text-sm">
              {t(
                'workflowOrchestration.execution.terminationResidualHint',
                '系统会继续尝试取消，请稍后刷新。已请求取消 {total} 个关联作业，其中 {succeeded} 个已确认。',
                { total: summary.total, succeeded: summary.succeeded },
              )}
            </p>
            <ul className="m-0 list-disc pl-5 text-sm">
              {summary.items.map((item) => (
                <li key={item.task_id}>
                  {item.ok
                    ? t('workflowOrchestration.execution.terminationJobCancelled', '作业 {taskId} 已取消', { taskId: item.task_id })
                    : t('workflowOrchestration.execution.terminationJobCancelFailed', '作业 {taskId} 取消失败', { taskId: item.task_id })}
                </li>
              ))}
            </ul>
          </div>
        )}
      />
    );
  }

  if (execution.status === 'TERMINATING') {
    return (
      <Alert
        className="mt-3"
        type="info"
        showIcon
        data-testid="execution-termination-progress-alert"
        message={t(
          'workflowOrchestration.execution.terminationProgressTitle',
          '正在停止关联作业（{succeeded}/{total} 已确认取消）',
          { succeeded: summary.succeeded, total: summary.total },
        )}
      />
    );
  }

  return null;
}
