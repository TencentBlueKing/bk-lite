'use client';

import { Fragment, useRef, useState } from 'react';
import { Alert, Button, Drawer, Empty, Modal, Popconfirm, Spin, Table, Tag } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useTransferApi } from '@/app/cmdb/api/transfer';
import type { TransferTask } from '@/app/cmdb/types/transfer';
import { downloadBlobFile } from '@/app/cmdb/(pages)/assetData/components/exportDownload';
import { parseErrorReport, type ErrorReportTable } from './errorReport';

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
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState('');
  const [preview, setPreview] = useState<ErrorReportTable>({ columns: [], rows: [] });
  const viewErrors = async (task: TransferTask) => {
    setBusy(`${task.task_id}:view_errors`);
    setPreviewOpen(true);
    setPreviewLoading(true);
    setPreviewError('');
    setPreview({ columns: [], rows: [] });
    try {
      const blob = await api.download(task.task_id, 'errors');
      setPreview(await parseErrorReport(await blob.arrayBuffer()));
    } catch (failure) {
      setPreviewError(failure instanceof Error ? failure.message : t('Transfer.requestFailed'));
    } finally {
      setPreviewLoading(false);
      setBusy('');
    }
  };
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
                {task.failure && <div>{t('Transfer.failureStage')}: {t(`Transfer.phase.${task.failure.stage}`)}</div>}
                {task.status === 'failed' && <div>{t('Transfer.taskId')}: {task.task_id}</div>}
                <div>{t('Transfer.expires')}: {new Date(task.expires_at).toLocaleString()}</div>
                {task.status === 'running' && <div>{t(`Transfer.phase.${task.phase}`)} · {task.processed_rows}{task.total_rows !== null ? ` / ${task.total_rows}` : ''} {t('Transfer.rows')}</div>}
              </div>
              {Object.keys(task.summary).length > 0 && <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1">
                {Object.entries(task.summary).filter(([, value]) => typeof value === 'number' || value === null).map(([key, value]) =>
                  <span key={key}>{t(`Transfer.count.${key}`)}: {value ?? t('Transfer.unknown')}</span>)}
              </div>}
              {task.message && <p className="mt-2 break-words text-[var(--color-text-2)]">{task.message}</p>}
              {task.failure?.result_uncertain && <p className="mt-2 text-[var(--color-text-2)]">{t('Transfer.partialWriteHint')}</p>}
              {task.status === 'failed' && task.type === 'import' && !task.failure?.result_uncertain &&
                ['created', 'updated', 'created_relations'].some(key => Number(task.summary[key]) > 0) &&
                <p className="mt-2 text-[var(--color-text-2)]">{t('Transfer.writesRetained')}</p>}
              {task.failure?.execution_pending && <p className="mt-2 text-[var(--color-text-3)]">{t('Transfer.executionPending')}</p>}
              <div className="mt-3 flex flex-wrap gap-2">
                {task.available_actions.map(action => (
                  <Fragment key={action}>
                    {action === 'download_errors' && (
                      <Button size="small" loading={busy === `${task.task_id}:view_errors`} disabled={Boolean(busy) && busy !== `${task.task_id}:view_errors`}
                        onClick={() => void viewErrors(task)}>{t('Transfer.view_errors')}</Button>
                    )}
                    {action === 'delete' ? (
                      <Popconfirm title={t('Transfer.deleteConfirm')} onConfirm={() => operate(task, action)}>
                        <Button size="small" disabled={Boolean(busy)}>{t('Transfer.delete')}</Button>
                      </Popconfirm>
                    ) : (
                      <Button size="small" loading={busy === `${task.task_id}:${action}`} disabled={Boolean(busy) && busy !== `${task.task_id}:${action}`}
                        onClick={() => void operate(task, action)}>{t(`Transfer.${action}`)}</Button>
                    )}
                  </Fragment>
                ))}
              </div>
            </article>
          ))}
        </div>
      </Spin>
      <Modal
        title={t('Transfer.view_errors')}
        open={previewOpen}
        width={840}
        onCancel={() => setPreviewOpen(false)}
        footer={<Button type="primary" onClick={() => setPreviewOpen(false)}>{t('common.close')}</Button>}
      >
        {previewError && <Alert type="error" showIcon message={previewError} className="mb-4" />}
        <Table
          size="small"
          loading={previewLoading}
          rowKey="key"
          pagination={preview.rows.length > 10 ? { pageSize: 10 } : false}
          scroll={{ y: 420 }}
          locale={{ emptyText: <Empty description={t('Transfer.errorsEmpty')} /> }}
          columns={preview.columns.map((column) => ({
            title: column,
            dataIndex: column,
            render: (value: string) => <span className="whitespace-pre-wrap break-words">{value}</span>,
          }))}
          dataSource={preview.rows}
        />
      </Modal>
    </Drawer>
  );
}
