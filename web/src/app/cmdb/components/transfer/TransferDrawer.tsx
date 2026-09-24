'use client';

import { useRef, useState } from 'react';
import { Alert, Button, Drawer, Empty, Popconfirm, Spin, Tag } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useTransferApi } from '@/app/cmdb/api/transfer';
import type { TransferTask } from '@/app/cmdb/types/transfer';
import { downloadBlobFile } from '@/app/cmdb/(pages)/assetData/components/exportDownload';

interface Props {
  open: boolean;
  onClose: () => void;
  tasks: TransferTask[];
  error: string;
  loading: boolean;
  onRefresh: () => Promise<void>;
}

export default function TransferDrawer({ open, onClose, tasks, error, loading, onRefresh }: Props) {
  const { t } = useTranslation();
  const api = useTransferApi();
  const retryKeys = useRef<Record<string, string>>({});
  const [busy, setBusy] = useState('');
  const [actionError, setActionError] = useState('');
  const operate = async (task: TransferTask, action: string) => {
    setBusy(`${task.task_id}:${action}`);
    setActionError('');
    try {
      if (action === 'cancel') await api.cancel(task.task_id);
      else if (action === 'delete') await api.remove(task.task_id);
      else if (action === 'retry') {
        retryKeys.current[task.task_id] ||= crypto.randomUUID();
        await api.retry(task.task_id, retryKeys.current[task.task_id]);
        delete retryKeys.current[task.task_id];
      } else {
        const artifact = action === 'download_errors' ? 'errors' : 'result';
        const blob = await api.download(task.task_id, artifact);
        downloadBlobFile(blob, `${task.model_id}-${artifact}.xlsx`);
      }
      await onRefresh();
    } catch (failure) {
      setActionError(failure instanceof Error ? failure.message : t('Transfer.requestFailed'));
    } finally { setBusy(''); }
  };
  return (
    <Drawer title={t('Transfer.title')} open={open} onClose={onClose} width={620}
      extra={<Button loading={loading} onClick={() => void onRefresh()}>{t('common.refresh')}</Button>}>
      <Alert type="info" showIcon message={t('Transfer.retention')} className="mb-4" />
      {(error || actionError) && <Alert type="error" showIcon message={error || actionError} className="mb-4" />}
      <Spin spinning={loading && tasks.length === 0}>
        {!tasks.length && <Empty description={t('Transfer.empty')} />}
        <div className="flex flex-col gap-4">
          {tasks.map(task => (
            <article key={task.task_id} className="rounded-lg border border-[var(--color-border-1)] p-4">
              <div className="mb-2 flex items-center justify-between gap-3">
                <strong className="truncate">{t(`Transfer.${task.type}`)} · {task.model_name}</strong>
                <Tag color={task.status === 'succeeded' ? 'success' : task.status === 'running' ? 'processing' :
                ['failed', 'interrupted'].includes(task.status) ? 'error' : task.status === 'partial_success' ? 'warning' : 'default'}>
                  {t(`Transfer.status.${task.status}`)}
                </Tag>
              </div>
              <div className="space-y-1 text-sm text-[var(--color-text-3)]">
                <div>{t('Transfer.organization')}: {task.team_id} · {task.scope ? t(`Transfer.scope.${task.scope}`) : task.filename}</div>
                <div>{t('Transfer.created')}: {new Date(task.created_at).toLocaleString()}</div>
                {task.type === 'export' && task.status === 'succeeded' && task.finished_at && (
                  <div>{t('Transfer.succeededAt')}: {new Date(task.finished_at).toLocaleString()}</div>
                )}
                <div>{t('Transfer.expires')}: {new Date(task.expires_at).toLocaleString()}</div>
                {task.status === 'running' && <div>{t(`Transfer.phase.${task.phase}`)} · {task.processed_rows}{task.total_rows !== null ? ` / ${task.total_rows}` : ''} {t('Transfer.rows')}</div>}
              </div>
              {Object.keys(task.summary).length > 0 && <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1">
                {Object.entries(task.summary).filter(([, value]) => typeof value === 'number').map(([key, value]) =>
                  <span key={key}>{t(`Transfer.count.${key}`)}: {value}</span>)}
              </div>}
              {task.message && <p className="mt-2 break-words text-[var(--color-text-2)]">{task.message}</p>}
              <div className="mt-3 flex flex-wrap gap-2">
                {task.available_actions.map(action => action === 'delete' ? (
                  <Popconfirm key={action} title={t('Transfer.deleteConfirm')} onConfirm={() => operate(task, action)}>
                    <Button size="small" disabled={Boolean(busy)}>{t('Transfer.delete')}</Button>
                  </Popconfirm>
                ) : <Button key={action} size="small" loading={busy === `${task.task_id}:${action}`} disabled={Boolean(busy) && busy !== `${task.task_id}:${action}`}
                  onClick={() => void operate(task, action)}>{t(`Transfer.${action}`)}</Button>)}
              </div>
            </article>
          ))}
        </div>
      </Spin>
    </Drawer>
  );
}
