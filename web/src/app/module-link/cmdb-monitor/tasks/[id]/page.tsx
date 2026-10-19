'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Button, Card, Checkbox, Modal, Select, Space, Table, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useParams } from 'next/navigation';
import { applySameOriginNavigation } from '@/console-layout';
import { useTranslation } from '@/utils/i18n';
import useMonitorApi from '@/app/monitor/api';
import MonitorBindModal from '@/app/cmdb/(pages)/assetData/detail/baseInfo/MonitorBindModal';
import {
  useModuleLinkApi,
  type CmdbMonitorTask,
  type CmdbMonitorTaskItem,
} from '@/app/module-link/api';

const STATUS_ORDER = [
  'needs_object',
  'not_found',
  'conflict',
  'ok',
  'already_linked',
  'failed',
  'skipped_model',
] as const;

const CmdbMonitorTaskPage = () => {
  const { t } = useTranslation();
  const params = useParams();
  const taskId = String(params?.id || '');
  const { getCmdbMonitorTask, cancelCmdbMonitorTask, assignCmdbMonitorObject } =
    useModuleLinkApi();
  const { getMonitorObject } = useMonitorApi();
  const [task, setTask] = useState<CmdbMonitorTask | null>(null);
  const [loading, setLoading] = useState(false);
  const [objects, setObjects] = useState<Array<{ id: number; name: string }>>([]);
  const [assignOpen, setAssignOpen] = useState(false);
  const [assignItems, setAssignItems] = useState<CmdbMonitorTaskItem[]>([]);
  const [objectName, setObjectName] = useState<string>();
  const [remember, setRemember] = useState(false);
  const [assigning, setAssigning] = useState(false);
  const [bindItem, setBindItem] = useState<CmdbMonitorTaskItem | null>(null);

  const loadTask = useCallback(async () => {
    if (!taskId) return;
    setLoading(true);
    try {
      const data = await getCmdbMonitorTask(taskId);
      setTask(data);
    } catch {
      setTask(null);
      message.error(t('ModuleLink.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [getCmdbMonitorTask, taskId, t]);

  useEffect(() => {
    void loadTask();
  }, [loadTask]);

  useEffect(() => {
    void getMonitorObject()
      .then((rows: Array<{ id: number; name: string }>) => {
        setObjects(Array.isArray(rows) ? rows : []);
      })
      .catch(() => setObjects([]));
  }, [getMonitorObject]);

  const items = task?.items || [];
  const drafts = task?.drafts || [];
  const summary = task?.summary || {};

  const columns: ColumnsType<CmdbMonitorTaskItem> = useMemo(
    () => [
      { title: t('ModuleLink.instName'), dataIndex: 'inst_name', ellipsis: true },
      { title: t('ModuleLink.model'), dataIndex: 'model_id', width: 140 },
      { title: t('ModuleLink.ip'), dataIndex: 'ip', width: 140 },
      { title: t('ModuleLink.monitorId'), dataIndex: 'monitor_id', ellipsis: true },
    ],
    [t],
  );

  const openAssign = (rows: CmdbMonitorTaskItem[]) => {
    setAssignItems(rows);
    setObjectName(undefined);
    setRemember(false);
    setAssignOpen(true);
  };

  const handleAssign = async () => {
    if (!taskId || !objectName) {
      message.warning(t('ModuleLink.objectNameRequired'));
      return;
    }
    setAssigning(true);
    try {
      const data = await assignCmdbMonitorObject(taskId, {
        item_ids: assignItems.map((item) => item.id),
        object_name: objectName,
        remember,
      });
      setTask(data);
      setAssignOpen(false);
      message.success(t('ModuleLink.assignSuccess'));
    } catch {
      message.error(t('ModuleLink.loadFailed'));
    } finally {
      setAssigning(false);
    }
  };

  const goConfigure = (objectNameForDraft: string) => {
    const draft = drafts.find((item) => item.object_name === objectNameForDraft);
    const object = objects.find((item) => item.name === objectNameForDraft);
    if (!draft || !object) {
      message.error(t('ModuleLink.missingObject'));
      return;
    }
    applySameOriginNavigation(
      `/monitor/integration/list?objId=${encodeURIComponent(String(object.id))}&cmdb_draft=${encodeURIComponent(draft.id)}`,
      { explicitNewWindow: true },
    );
  };

  const handleCancel = () => {
    Modal.confirm({
      centered: true,
      title: t('ModuleLink.cancelConfirm'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      onOk: async () => {
        const data = await cancelCmdbMonitorTask(taskId);
        setTask(data);
        message.success(t('ModuleLink.cancelled'));
      },
    });
  };

  const statusLabel = (status: string) => {
    const keys: Record<string, string> = {
      ok: 'ModuleLink.statusOk',
      already_linked: 'ModuleLink.statusAlreadyLinked',
      not_found: 'ModuleLink.statusNotFound',
      conflict: 'ModuleLink.statusConflict',
      failed: 'ModuleLink.statusFailed',
      skipped_model: 'ModuleLink.statusSkipped',
      needs_object: 'ModuleLink.statusNeedsObject',
    };
    return t(keys[status] || status);
  };

  const statusHint = (status: string) => {
    const keys: Record<string, string> = {
      ok: 'ModuleLink.statusOkHint',
      already_linked: 'ModuleLink.statusAlreadyLinkedHint',
    };
    return keys[status] ? t(keys[status]) : '';
  };

  const visibleStatuses = STATUS_ORDER.filter((status) => {
    if (items.some((item) => item.status === status)) return true;
    return Number(summary[status] || 0) > 0;
  });

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 overflow-auto bg-[var(--color-bg-1)] p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="m-0 text-lg font-semibold text-[var(--color-text-1)]">
            {t('ModuleLink.taskTitle')}
          </h1>
          <p className="mt-1 mb-0 text-[var(--color-text-2)]">{t('ModuleLink.taskSubtitle')}</p>
        </div>
        <Space>
          <Button onClick={() => void loadTask()} loading={loading}>
            {t('ModuleLink.refresh')}
          </Button>
          <Button danger disabled={!task || task.status === 'cancelled'} onClick={handleCancel}>
            {t('ModuleLink.cancel')}
          </Button>
        </Space>
      </div>
      {visibleStatuses.length > 0 ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {visibleStatuses.map((status) => (
            <Card key={status} size="small">
              <div className="text-[var(--color-text-3)]">{statusLabel(status)}</div>
              <div className="text-xl font-semibold text-[var(--color-text-1)]">
                {Number(summary[status] ?? items.filter((item) => item.status === status).length)}
              </div>
            </Card>
          ))}
        </div>
      ) : null}
      {visibleStatuses.map((status) => {
        const rows = items.filter((item) => item.status === status);
        const extra =
          status === 'not_found' ? (
            <Space wrap>
              {[...new Set(rows.map((item) => item.object_name).filter(Boolean))].map((name) => (
                <Button type="link" key={name} onClick={() => goConfigure(name)}>
                  {name} · {t('ModuleLink.goConfigure')}
                </Button>
              ))}
            </Space>
          ) : status === 'needs_object' ? (
            <Button type="link" disabled={!rows.length} onClick={() => openAssign(rows)}>
              {t('ModuleLink.assignObject')}
            </Button>
          ) : null;
        return (
          <Card
            key={`table-${status}`}
            size="small"
            title={statusLabel(status)}
            extra={extra}
          >
            {status === 'not_found' ? (
              <p className="mt-0 text-[var(--color-text-3)]">{t('ModuleLink.configureHint')}</p>
            ) : statusHint(status) ? (
              <p className="mt-0 text-[var(--color-text-3)]">{statusHint(status)}</p>
            ) : null}
            <Table
              rowKey="id"
              size="small"
              pagination={false}
              dataSource={rows}
              columns={
                status === 'conflict'
                  ? [
                    ...columns,
                    {
                      title: '',
                      key: 'bind',
                      width: 120,
                      render: (_: unknown, record: CmdbMonitorTaskItem) => (
                        <Button type="link" onClick={() => setBindItem(record)}>
                          {t('ModuleLink.bind')}
                        </Button>
                      ),
                    },
                  ]
                  : columns
              }
              locale={{ emptyText: t('ModuleLink.empty') }}
            />
          </Card>
        );
      })}
      <Modal
        open={assignOpen}
        title={t('ModuleLink.assignObject')}
        onCancel={() => setAssignOpen(false)}
        onOk={() => void handleAssign()}
        confirmLoading={assigning}
        destroyOnClose
      >
        <p className="text-[var(--color-text-2)]">{t('ModuleLink.assignObjectHelp')}</p>
        <Select
          className="w-full"
          showSearch
          optionFilterProp="label"
          placeholder={t('ModuleLink.objectName')}
          value={objectName}
          onChange={setObjectName}
          options={objects.map((item) => ({ value: item.name, label: item.name }))}
        />
        <Checkbox
          className="mt-3"
          checked={remember}
          onChange={(event) => setRemember(event.target.checked)}
        >
          {t('ModuleLink.rememberMapping')}
        </Checkbox>
      </Modal>
      <MonitorBindModal
        open={Boolean(bindItem)}
        instUuid={bindItem?.inst_uuid || ''}
        alreadyLinked={false}
        onCancel={() => setBindItem(null)}
        onSuccess={() => {
          setBindItem(null);
          void loadTask();
        }}
      />
    </div>
  );
};

export default CmdbMonitorTaskPage;
