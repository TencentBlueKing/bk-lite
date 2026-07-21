'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Badge, Button, Card, Empty, Input, Space, Spin, Switch, Tabs, message } from 'antd';
import CustomTable from '@/components/custom-table';
import { useNodeMgmtSyncApi } from '@/app/cmdb/api';
import { useTranslation } from '@/utils/i18n';
import type {
  CollectTaskMessage,
  NodeMgmtSyncTask,
  NodeMgmtSyncRun,
  NodeMgmtSyncItem,
  NodeMgmtSyncDisplayPayload,
  TaskData,
} from '@/app/cmdb/types/autoDiscovery';
import {
  NODE_MGMT_SYNC_STATUS_BADGE,
  createNodeMgmtSyncRequestGuard,
  getNodeMgmtSyncDisplayEmptyStateKey,
  getNodeMgmtSyncEmptyStateKey,
  getNodeMgmtSyncReasonTextKey,
  getNodeMgmtSyncStatusTextKey,
  normalizeNodeMgmtSyncStatus,
} from './nodeMgmtSyncViewModel';
import type { NodeMgmtSyncGuardToken } from './nodeMgmtSyncViewModel';

interface NodeMgmtSyncDetailProps {
  open: boolean;
}

const StatisticCard = ({ title, value, accentClass }: { title: string; value: number; accentClass: string }) => {
  return (
    <Card size="small" className="shadow-sm">
      <div className="text-xs text-[var(--color-text-3)] mb-1">{title}</div>
      <div className={`text-3xl font-semibold ${accentClass}`}>{value}</div>
    </Card>
  );
};

const EMPTY_TASK_DATA: TaskData = { data: [], count: 0 };

const NodeMgmtSyncDetail: React.FC<NodeMgmtSyncDetailProps> = ({ open }) => {
  const { t } = useTranslation();
  const api = useNodeMgmtSyncApi();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
  const [task, setTask] = useState<NodeMgmtSyncTask | null>(null);
  const [displayPayload, setDisplayPayload] = useState<NodeMgmtSyncDisplayPayload | null>(null);
  const [activeTab, setActiveTab] = useState('add');
  const [searchText, setSearchText] = useState('');
  const [pendingSearchText, setPendingSearchText] = useState('');
  const requestGuard = useRef(createNodeMgmtSyncRequestGuard()).current;
  const savingRef = useRef(false);

  const fetchData = async (showFeedback = false, mutationToken?: NodeMgmtSyncGuardToken) => {
    const requestToken = requestGuard.beginRequest();
    if (!requestGuard.isRequestCurrent(requestToken)) {
      return false;
    }
    try {
      setLoading(true);
      setLoadFailed(false);
      const [taskRes, displayRes] = await Promise.all([
        api.getNodeMgmtSyncTask(),
        api.getNodeMgmtSyncDisplay(),
      ]);
      if (!requestGuard.isRequestCurrent(requestToken)
        || (mutationToken && !requestGuard.isMutationCurrent(mutationToken))) {
        return false;
      }
      setTask(taskRes);
      setDisplayPayload(displayRes);
      if (showFeedback) {
        message.success(t('Collection.nodeMgmtSync.refreshSuccess'));
      }
      return true;
    } catch (error) {
      if (!requestGuard.isRequestCurrent(requestToken)
        || (mutationToken && !requestGuard.isMutationCurrent(mutationToken))) {
        return false;
      }
      console.error('Failed to fetch node management sync data:', error);
      setLoadFailed(true);
      message.error(t('Collection.nodeMgmtSync.loadFailed'));
      return false;
    } finally {
      if (requestGuard.isRequestCurrent(requestToken)
        && (!mutationToken || requestGuard.isMutationCurrent(mutationToken))) {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    if (!open) {
      requestGuard.close();
      savingRef.current = false;
      setSaving(false);
      return;
    }
    requestGuard.open();
    void fetchData();
    return () => requestGuard.close();
  }, [open]);

  const handleConfigChange = async (patch: Partial<NodeMgmtSyncTask>) => {
    if (!task || savingRef.current) {
      return;
    }
    savingRef.current = true;
    const mutationToken = requestGuard.beginMutation();
    setLoading(false);
    const nextTask = { ...task, ...patch };
    setTask(nextTask);
    try {
      setSaving(true);
      const response = await api.updateNodeMgmtSyncTask(patch);
      if (!requestGuard.isMutationCurrent(mutationToken)) {
        return;
      }
      setTask(response);
      await fetchData(false, mutationToken);
      if (requestGuard.isMutationCurrent(mutationToken)) {
        message.success(t('successfulSetted'));
      }
    } catch (error) {
      if (!requestGuard.isMutationCurrent(mutationToken)) {
        return;
      }
      console.error('Failed to update node management sync config:', error);
      message.error(t('Collection.nodeMgmtSync.saveFailed'));
      setTask(task);
    } finally {
      if (requestGuard.isMutationCurrent(mutationToken)) {
        savingRef.current = false;
        setSaving(false);
      }
    }
  };

  const syncRun: NodeMgmtSyncRun | null = displayPayload?.run || null;
  const normalizedRunStatus = normalizeNodeMgmtSyncStatus(syncRun?.status);
  const runStatus = normalizedRunStatus.status;
  const reasonCode = syncRun?.reason_code
    || task?.health?.reason_code
    || task?.reconcile_error_code
    || '';
  const detail = displayPayload?.detail;
  const displayMessage: CollectTaskMessage = displayPayload?.message || syncRun?.message || {
    all: 0,
    add: 0,
    update: 0,
    delete: 0,
    association: 0,
    add_error: 0,
    add_success: 0,
    delete_error: 0,
    delete_success: 0,
    update_error: 0,
    update_success: 0,
    association_error: 0,
    association_success: 0,
  };
  const todoItems = detail?.todo || [];
  const healthAlert = useMemo(() => {
    if (loadFailed) {
      return { type: 'error' as const, textKey: 'Collection.nodeMgmtSync.empty.queryFailed' };
    }
    if (task?.health?.schedule_status === 'degraded' || task?.health?.node_config_status === 'degraded') {
      return { type: 'error' as const, textKey: getNodeMgmtSyncReasonTextKey(reasonCode) };
    }
    if (task?.health?.node_config_status === 'waiting_sync' || runStatus === 'waiting_sync') {
      return { type: 'warning' as const, textKey: 'Collection.nodeMgmtSync.status.waitingSync' };
    }
    if (task?.health?.schedule_status === 'reconciling' || task?.health?.node_config_status === 'reconciling') {
      return { type: 'info' as const, textKey: 'Collection.nodeMgmtSync.health.reconciling' };
    }
    if (normalizedRunStatus.isUnknown) {
      return { type: 'error' as const, textKey: 'Collection.nodeMgmtSync.status.unknown' };
    }
    if (runStatus && ['blocked', 'failed', 'timeout'].includes(runStatus)) {
      return { type: 'error' as const, textKey: getNodeMgmtSyncReasonTextKey(reasonCode) };
    }
    if (runStatus === 'submitted') {
      return { type: 'info' as const, textKey: 'Collection.nodeMgmtSync.status.submitted' };
    }
    if (runStatus === 'partial_success') {
      return { type: 'warning' as const, textKey: 'Collection.nodeMgmtSync.status.partialSuccess' };
    }
    return null;
  }, [loadFailed, normalizedRunStatus.isUnknown, reasonCode, runStatus, task]);
  const emptyStateKey = displayPayload
    ? getNodeMgmtSyncDisplayEmptyStateKey(displayPayload, loadFailed)
    : getNodeMgmtSyncEmptyStateKey({
      status: runStatus,
      reasonCode,
      total: displayMessage.all || 0,
      loadFailed,
    });
  useEffect(() => {
    const tabOrder = ['add', 'update', 'delete', 'relation', 'raw_data'] as const;
    const firstWithData = tabOrder.find((key) => (detail?.[key]?.count || 0) > 0);
    if (firstWithData) {
      setActiveTab(firstWithData);
    }
  }, [detail]);

  const tabMap = useMemo(
    () => ({
      add: detail?.add || EMPTY_TASK_DATA,
      update: detail?.update || EMPTY_TASK_DATA,
      delete: detail?.delete || EMPTY_TASK_DATA,
      relation: detail?.relation || EMPTY_TASK_DATA,
      raw_data: detail?.raw_data || EMPTY_TASK_DATA,
    }),
    [detail]
  );

  const filteredRows = useMemo(() => {
    const rows = (tabMap[activeTab as keyof typeof tabMap] || EMPTY_TASK_DATA).data as NodeMgmtSyncItem[];
    if (!searchText) {
      return rows;
    }
    return rows.filter((item) => {
      const source = `${item.inst_name || item.name || ''} ${item.ip_addr || item.ip || ''} ${item.cloud_name || ''}`.toLowerCase();
      return source.includes(searchText.toLowerCase());
    });
  }, [activeTab, searchText, tabMap]);

  const columns = useMemo(() => {
    if (activeTab === 'raw_data') {
      return [
        {
          title: t('Collection.nodeMgmtSync.table.objectType'),
          dataIndex: 'model_id',
          render: (value: string) => value || 'host',
        },
        {
          title: t('Collection.nodeMgmtSync.table.instanceName'),
          dataIndex: 'inst_name',
          render: (_: string, record: NodeMgmtSyncItem) => record.inst_name || record.name || '--',
        },
        {
          title: 'IP',
          dataIndex: 'ip_addr',
          render: (_: string, record: NodeMgmtSyncItem) => record.ip_addr || record.ip || '--',
        },
        {
          title: t('organization'),
          dataIndex: 'organization',
          render: (value: Array<number | string>) =>
            Array.isArray(value) && value.length ? value.join(', ') : '--',
        },
      ];
    }

    return [
      {
        title: t('Collection.nodeMgmtSync.table.objectType'),
        dataIndex: 'model_id',
        render: (value: string) => value || 'host',
      },
      {
        title: t('Collection.nodeMgmtSync.table.instanceName'),
        dataIndex: 'inst_name',
        render: (value: string) => value || '--',
      },
      {
        title: 'IP',
        dataIndex: 'ip_addr',
        render: (value: string, record: NodeMgmtSyncItem) => value || record.ip || '--',
      },
      {
        title: t('Collection.nodeMgmtSync.table.status'),
        dataIndex: '_status',
        render: (value: string) => value || '--',
      },
      {
        title: t('Collection.nodeMgmtSync.table.errorReason'),
        dataIndex: '_error',
        render: (value: string) => value || '--',
      },
    ];
  }, [activeTab, t]);

  const tabItems = useMemo(() => {
    const tabs = [
      { key: 'add', label: `${t('Collection.syncStatus.add')} (${tabMap.add.count || 0})` },
      { key: 'update', label: `${t('Collection.syncStatus.update')} (${tabMap.update.count || 0})` },
      { key: 'delete', label: `${t('Collection.syncStatus.delete')} (${tabMap.delete.count || 0})` },
      { key: 'relation', label: `${t('Collection.nodeMgmtSync.conflict')} (${tabMap.relation.count || 0})` },
      { key: 'raw_data', label: `${t('Collection.taskDetail.rawData')} (${tabMap.raw_data.count || 0})` },
    ];
    return tabs;
  }, [t, tabMap]);

  if (!open) {
    return null;
  }

  return (
    <div className="flex flex-col gap-4">
      {loading ? (
        <div className="py-8 flex justify-center">
          <Spin />
        </div>
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3 rounded border border-[var(--color-border-1)] bg-[var(--color-bg-1)] p-4">
            <div className="text-sm text-[var(--color-text-2)]">
              <div>
                {t('Collection.nodeMgmtSync.lastSyncTime')}：{task?.last_sync_at || '--'}
              </div>
              <div>
                {t('Collection.nodeMgmtSync.lastCollectTime')}：{task?.last_collect_at || '--'}
              </div>
            </div>
            <Space size="large" wrap>
              <Space>
                <span>{t('Collection.nodeMgmtSync.autoSync')}</span>
                <Switch
                  checked={task?.auto_sync_enabled}
                  disabled={saving}
                  loading={saving}
                  onChange={(checked) => void handleConfigChange({ auto_sync_enabled: checked })}
                />
              </Space>
              <Space>
                <span>{t('Collection.nodeMgmtSync.autoCollect')}</span>
                <Switch
                  checked={task?.auto_collect_enabled}
                  disabled={saving}
                  loading={saving}
                  onChange={(checked) => void handleConfigChange({ auto_collect_enabled: checked })}
                />
              </Space>
              <Button disabled={saving} loading={loading} onClick={() => void fetchData(true)}>
                {t('common.refresh')}
              </Button>
            </Space>
          </div>

          {healthAlert ? (
            <Alert
              type={healthAlert.type}
              message={t(healthAlert.textKey)}
              showIcon
            />
          ) : null}

          {runStatus ? (
            <div className="text-sm text-[var(--color-text-2)]">
              {t('Collection.nodeMgmtSync.runStatus')}：
              <Badge
                status={NODE_MGMT_SYNC_STATUS_BADGE[runStatus]}
                text={t(getNodeMgmtSyncStatusTextKey(runStatus, normalizedRunStatus.isUnknown))}
              />
            </div>
          ) : null}

          <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
            <StatisticCard
              title={t('Collection.nodeMgmtSync.totalDiscovered')}
              value={displayMessage.all || 0}
              accentClass="text-[var(--color-success)]"
            />
            <StatisticCard
              title={t('Collection.nodeMgmtSync.addData')}
              value={displayMessage.add || 0}
              accentClass="text-[var(--color-success)]"
            />
            <StatisticCard
              title={t('Collection.nodeMgmtSync.updateData')}
              value={displayMessage.update || 0}
              accentClass="text-[var(--color-primary)]"
            />
            <StatisticCard
              title={t('Collection.nodeMgmtSync.deleteData')}
              value={displayMessage.delete || 0}
              accentClass="text-[var(--color-danger)]"
            />
          </div>

          {displayMessage.association ? (
            <Alert
              type="warning"
              message={t('Collection.nodeMgmtSync.conflictNotice', undefined, {
                count: String(displayMessage.association || 0),
              })}
              showIcon
            />
          ) : null}

          {todoItems.length ? (
            <Alert
              type="info"
              message={t('Collection.nodeMgmtSync.todoNotice', undefined, { count: String(todoItems.length) })}
              showIcon
            />
          ) : null}

          <div className="flex items-center gap-3">
            <Input.Search
              allowClear
              className="w-80"
              placeholder={t('Collection.nodeMgmtSync.searchPlaceholder')}
              value={pendingSearchText}
              onChange={(e) => setPendingSearchText(e.target.value)}
              onSearch={(value) => setSearchText(value)}
            />
          </div>

          <Tabs activeKey={activeTab} onChange={setActiveTab} items={tabItems} />

          {!filteredRows.length ? (
            <div className="py-10">
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t(emptyStateKey)} />
            </div>
          ) : (
            <CustomTable
              rowKey={(record: NodeMgmtSyncItem) => record.id || record.inst_name || record.ip_addr || record.ip || record.name}
              columns={columns}
              dataSource={filteredRows}
              pagination={{ showSizeChanger: true, showTotal: (total) => `共 ${total} 条` }}
              scroll={{ y: 'calc(100vh - 520px)' }}
            />
          )}
        </>
      )}
    </div>
  );
};

export default NodeMgmtSyncDetail;
