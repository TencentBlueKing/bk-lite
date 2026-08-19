'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Button, Checkbox, Drawer, Modal, Space, Spin, Tag, message } from 'antd';
import type { TablePaginationConfig } from 'antd';
import Introduction from '@/components/introduction';
import CustomTable from '@/components/custom-table';
import PermissionWrapper from '@/components/permission';
import SearchActionBar from '@/components/search-action-bar';
import { useScanApi } from '@/app/cmdb/api';
import { useTranslation } from '@/utils/i18n';
import ScanTaskDrawer, { SCAN_FAMILIES } from './ScanTaskDrawer';

interface ScanExecutionSummary {
  id: number;
  status: string;
  target_count: number;
  received_count: number;
}

interface ScanTaskItem {
  id: number;
  name: string;
  families: string[];
  updated_at: string;
  latest_execution?: ScanExecutionSummary | null;
}

interface ScanHitItem {
  id: number;
  host: string;
  protocol: string;
  family_model_id?: string;
  status: string;
  soid: string;
  cmdb_model_id: string;
  credential_id: string;
  credential_label?: string;
  inst_uuid: string;
  port?: number;
  snapshot?: Record<string, unknown>;
}

const ACTIVE_STATUSES = new Set(['pending', 'running', 'finalizing']);
const HIT_PAGE_SIZE = 200;

const displayValue = (value: unknown) => {
  if (value === null || value === undefined || value === '') {
    return '--';
  }
  return String(value);
};

const ScanPage: React.FC = () => {
  const { t } = useTranslation();
  const {
    getScanList,
    executeScan,
    deleteScan,
    getScanExecution,
    getScanHits,
    generateCollect,
    pushMonitor,
  } = useScanApi();
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [tasks, setTasks] = useState<ScanTaskItem[]>([]);
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 });
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [hitsOpen, setHitsOpen] = useState(false);
  const [activeExecution, setActiveExecution] = useState<ScanExecutionSummary | null>(null);
  const [hits, setHits] = useState<ScanHitItem[]>([]);
  const [hitTotal, setHitTotal] = useState(0);
  const [selectedHitIds, setSelectedHitIds] = useState<number[]>([]);
  const [hitPage, setHitPage] = useState(1);
  const [hitsLoading, setHitsLoading] = useState(false);
  const [hitsLoadingMore, setHitsLoadingMore] = useState(false);
  const [batchLoading, setBatchLoading] = useState(false);
  const [executingTaskId, setExecutingTaskId] = useState<number | null>(null);

  const statusLabel = useMemo(
    () => ({
      pending: t('Scan.statusPending'),
      running: t('Scan.statusRunning'),
      finalizing: t('Scan.statusFinalizing'),
      completed: t('Scan.statusCompleted'),
      failed: t('Scan.statusFailed'),
      timed_out: t('Scan.statusTimedOut'),
    }),
    [t]
  );

  const familyLabel = useCallback(
    (modelId: string) => {
      const family = SCAN_FAMILIES.find((item) => item.modelId === modelId);
      return family ? t(family.labelKey) : modelId;
    },
    [t]
  );

  const fetchTasks = useCallback(
    async (page = pagination.current, pageSize = pagination.pageSize, search = keyword) => {
      setLoading(true);
      try {
        const data = await getScanList({
          page,
          page_size: pageSize,
          search,
        });
        setTasks(data.items || []);
        setPagination({
          current: page,
          pageSize,
          total: data.count || 0,
        });
      } finally {
        setLoading(false);
      }
    },
    [getScanList, keyword, pagination.current, pagination.pageSize]
  );

  useEffect(() => {
    fetchTasks(1, pagination.pageSize, '');
  }, []);

  const fetchHits = useCallback(
    async (executionId: number, page = 1, options?: { silent?: boolean }) => {
      const silent = Boolean(options?.silent);
      if (page <= 1 && !silent) {
        setHitsLoading(true);
      }
      if (page > 1) {
        setHitsLoadingMore(true);
      }
      try {
        const [execution, hitPageData] = await Promise.all([
          getScanExecution(executionId),
          getScanHits(executionId, { page, page_size: HIT_PAGE_SIZE }),
        ]);
        setActiveExecution({
          id: execution.id,
          status: execution.status,
          target_count: execution.target_count,
          received_count: execution.received_count,
        });
        setHits((prev) => (page <= 1 ? hitPageData.items || [] : [...prev, ...(hitPageData.items || [])]));
        setHitTotal(hitPageData.count || 0);
        setHitPage(page);
      } finally {
        if (page <= 1 && !silent) {
          setHitsLoading(false);
        }
        if (page > 1) {
          setHitsLoadingMore(false);
        }
      }
    },
    [getScanExecution, getScanHits]
  );

  useEffect(() => {
    if (!hitsOpen || !activeExecution || !ACTIVE_STATUSES.has(activeExecution.status)) {
      return;
    }
    const timer = window.setInterval(() => {
      fetchHits(activeExecution.id, hitPage, { silent: true }).catch((error) => console.error(error));
    }, 5000);
    return () => window.clearInterval(timer);
  }, [activeExecution, fetchHits, hitPage, hitsOpen]);

  const openHits = async (execution?: ScanExecutionSummary | null) => {
    if (!execution?.id) {
      return;
    }
    setHitsOpen(true);
    setSelectedHitIds([]);
    setHits([]);
    setHitTotal(0);
    try {
      await fetchHits(execution.id, 1);
    } catch (error) {
      console.error(error);
      message.error(t('Scan.noHits'));
    }
  };

  const handleExecute = async (task: ScanTaskItem) => {
    setExecutingTaskId(task.id);
    try {
      const execution = await executeScan(task.id);
      message.success(t('Scan.executeStarted'));
      await fetchTasks();
      await openHits({
        id: execution.id,
        status: execution.status,
        target_count: execution.target_count,
        received_count: execution.received_count,
      });
    } catch (error) {
      console.error(error);
      message.error(t('Scan.statusFailed'));
    } finally {
      setExecutingTaskId(null);
    }
  };

  const handleDelete = (task: ScanTaskItem) => {
    Modal.confirm({
      title: t('deleteTitle'),
      content: t('deleteContent'),
      okButtonProps: { danger: true },
      onOk: async () => {
        await deleteScan(task.id);
        message.success(t('successfullyDeleted'));
        fetchTasks();
      },
    });
  };

  const handleBatch = async (kind: 'collect' | 'monitor') => {
    if (!activeExecution?.id) {
      return;
    }
    if (!selectedHitIds.length) {
      message.warning(t('Scan.selectHits'));
      return;
    }
    setBatchLoading(true);
    try {
      if (kind === 'collect') {
        const result = await generateCollect(activeExecution.id, selectedHitIds);
        const created = result?.created ?? 0;
        const appended = result?.appended ?? 0;
        const skipped = result?.skipped ?? 0;
        const failed = result?.failed ?? 0;
        if (failed || skipped || appended || created === 0) {
          message.warning(
            t('Scan.generateCollectPartial', undefined, { created, appended, skipped, failed })
          );
        } else {
          message.success(t('Scan.generateCollectDone', undefined, { count: created }));
        }
      } else {
        const result = await pushMonitor(activeExecution.id, selectedHitIds);
        const pushed = result?.pushed ?? 0;
        const failed = result?.failed ?? 0;
        const skipped = result?.skipped ?? 0;
        const items = Array.isArray(result?.items) ? result.items : [];
        const reasons = items
          .filter((item: { status?: string; reason?: string; host?: string }) => item.status !== 'pushed' && item.reason)
          .slice(0, 3)
          .map((item: { host?: string; reason?: string }) => `${item.host || '-'}: ${item.reason}`)
          .join('；');
        if (failed || skipped || pushed === 0) {
          const summary = t('Scan.pushMonitorPartial', undefined, { pushed, failed, skipped });
          message.warning(reasons ? `${summary}（${reasons}）` : summary);
        } else {
          message.success(t('Scan.pushMonitorDone', undefined, { count: pushed }));
        }
      }
    } catch (error) {
      console.error(error);
      message.error(kind === 'collect' ? t('Scan.generateCollectFailed') : t('Scan.pushMonitorFailed'));
    } finally {
      setBatchLoading(false);
    }
  };

  const hitGroups = useMemo(() => {
    const order = SCAN_FAMILIES.map((item) => item.modelId);
    const grouped = new Map<string, ScanHitItem[]>();
    hits.forEach((hit) => {
      const key = hit.family_model_id || hit.protocol || 'unknown';
      const list = grouped.get(key) || [];
      list.push(hit);
      grouped.set(key, list);
    });
    return [...grouped.entries()].sort((a, b) => {
      const ai = order.indexOf(a[0]);
      const bi = order.indexOf(b[0]);
      return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi);
    });
  }, [hits]);

  const toggleHit = (hitId: number, checked: boolean) => {
    setSelectedHitIds((prev) => {
      if (checked) {
        return prev.includes(hitId) ? prev : [...prev, hitId];
      }
      return prev.filter((id) => id !== hitId);
    });
  };

  const toggleGroup = (groupHits: ScanHitItem[], checked: boolean) => {
    const ids = groupHits.map((item) => item.id);
    setSelectedHitIds((prev) => {
      if (checked) {
        return Array.from(new Set([...prev, ...ids]));
      }
      return prev.filter((id) => !ids.includes(id));
    });
  };

  const renderHitFacts = (hit: ScanHitItem) => {
    const snapshot = hit.snapshot || {};
    const family = hit.family_model_id || hit.protocol;
    if (family === 'host') {
      return [
        { label: t('Scan.hostname'), value: snapshot.hostname },
        { label: t('Scan.osType'), value: snapshot.os_type },
        { label: t('Scan.osName'), value: snapshot.os_name },
        { label: t('Scan.osVersion'), value: snapshot.os_version },
      ];
    }
    if (family === 'network') {
      return [
        { label: t('Scan.sysname'), value: snapshot.sysname || snapshot.inst_name },
        { label: t('Scan.deviceType'), value: snapshot.device_type || hit.cmdb_model_id },
        { label: t('Scan.brand'), value: snapshot.brand },
        { label: t('Scan.modelName'), value: snapshot.model },
        { label: t('Scan.soid'), value: hit.soid || snapshot.soid || snapshot.sysobjectid },
      ];
    }
    if (family === 'physcial_server') {
      return [
        { label: t('Scan.serialNumber'), value: snapshot.serial_number },
        { label: t('Scan.uuid'), value: snapshot.uuid },
        { label: t('Scan.model'), value: hit.cmdb_model_id },
      ];
    }
    return [
      { label: t('Scan.model'), value: hit.cmdb_model_id },
      { label: t('Scan.port'), value: hit.port || snapshot.port },
      { label: t('Scan.version'), value: snapshot.version || snapshot.db_version },
    ];
  };

  const columns = [
    { title: t('Scan.taskName'), dataIndex: 'name', key: 'name' },
    {
      title: t('Scan.families'),
      dataIndex: 'families',
      key: 'families',
      render: (families: string[] = []) => (
        <Space wrap>
          {families.map((item) => (
            <Tag key={item}>{familyLabel(item)}</Tag>
          ))}
        </Space>
      ),
    },
    {
      title: t('Scan.progress'),
      key: 'progress',
      render: (_: unknown, record: ScanTaskItem) => {
        const execution = record.latest_execution;
        if (!execution) {
          return '--';
        }
        return `${execution.received_count}/${execution.target_count}`;
      },
    },
    {
      title: t('Scan.status'),
      key: 'status',
      render: (_: unknown, record: ScanTaskItem) => {
        const status = record.latest_execution?.status;
        return status ? statusLabel[status as keyof typeof statusLabel] || status : '--';
      },
    },
    {
      title: t('common.actions'),
      key: 'actions',
      render: (_: unknown, record: ScanTaskItem) => (
        <Space>
          <PermissionWrapper requiredPermissions={['Execute']} permissionPath="/cmdb/assetManage/autoDiscovery/collection">
            <Button
              type="link"
              loading={executingTaskId === record.id}
              disabled={executingTaskId !== null && executingTaskId !== record.id}
              onClick={() => handleExecute(record)}
            >
              {t('Scan.execute')}
            </Button>
          </PermissionWrapper>
          <Button type="link" onClick={() => openHits(record.latest_execution)}>
            {t('Scan.hits')}
          </Button>
          <PermissionWrapper requiredPermissions={['Edit']} permissionPath="/cmdb/assetManage/autoDiscovery/collection">
            <Button
              type="link"
              onClick={() => {
                setEditId(record.id);
                setDrawerOpen(true);
              }}
            >
              {t('common.edit')}
            </Button>
          </PermissionWrapper>
          <PermissionWrapper requiredPermissions={['Delete']} permissionPath="/cmdb/assetManage/autoDiscovery/collection">
            <Button type="link" danger onClick={() => handleDelete(record)}>
              {t('common.delete')}
            </Button>
          </PermissionWrapper>
        </Space>
      ),
    },
  ];

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="shrink-0">
        <Introduction title={t('Scan.title')} message={t('Scan.message')} />
      </div>
      <div className="min-h-0 flex-1 overflow-hidden px-4 pt-3">
        <SearchActionBar
          searchProps={{
            placeholder: t('Collection.inputTaskPlaceholder'),
            allowClear: true,
            onSearch: (value) => {
              setKeyword(value);
              fetchTasks(1, pagination.pageSize, value);
            },
          }}
          actions={
            <PermissionWrapper requiredPermissions={['Add']} permissionPath="/cmdb/assetManage/autoDiscovery/collection">
              <Button
                type="primary"
                onClick={() => {
                  setEditId(null);
                  setDrawerOpen(true);
                }}
              >
                {t('Scan.addTask')}
              </Button>
            </PermissionWrapper>
          }
        />
        <div className="min-h-0 flex-1 overflow-hidden">
          <CustomTable
            loading={loading}
            rowKey="id"
            columns={columns}
            dataSource={tasks}
            pagination={{
              ...pagination,
              showSizeChanger: true,
              onChange: (page: number, pageSize: number) => fetchTasks(page, pageSize, keyword),
            } as TablePaginationConfig}
          />
        </div>
      </div>
      <ScanTaskDrawer
        open={drawerOpen}
        editId={editId}
        onClose={() => setDrawerOpen(false)}
        onSuccess={() => fetchTasks()}
      />
      <Drawer
        title={t('Scan.hits')}
        open={hitsOpen}
        width={1040}
        onClose={() => setHitsOpen(false)}
        footer={
          <div className="flex justify-end gap-2">
            <PermissionWrapper requiredPermissions={['Execute']} permissionPath="/cmdb/assetManage/autoDiscovery/collection">
              <Button loading={batchLoading} disabled={hitsLoading} onClick={() => handleBatch('collect')}>
                {t('Scan.generateCollect')}
              </Button>
            </PermissionWrapper>
            <PermissionWrapper requiredPermissions={['Execute']} permissionPath="/cmdb/assetManage/autoDiscovery/collection">
              <Button
                type="primary"
                loading={batchLoading}
                disabled={hitsLoading}
                onClick={() => handleBatch('monitor')}
              >
                {t('Scan.pushMonitor')}
              </Button>
            </PermissionWrapper>
          </div>
        }
      >
        <Spin spinning={hitsLoading}>
          <div className="mb-3 text-[var(--color-text-3)]">
            {t('Scan.progress')}: {activeExecution?.received_count ?? 0}/{activeExecution?.target_count ?? 0}
            {activeExecution?.status
              ? ` · ${statusLabel[activeExecution.status as keyof typeof statusLabel] || activeExecution.status}`
              : ''}
            {hitTotal ? ` · ${t('Scan.hitCount', undefined, { count: hitTotal })}` : ''}
          </div>
          <div className="flex min-h-[120px] flex-col gap-4">
            {!hitsLoading && hitGroups.length === 0 ? (
              <div className="text-[var(--color-text-3)]">{t('Scan.noHits')}</div>
            ) : (
              hitGroups.map(([family, groupHits]) => {
                const allSelected = groupHits.every((item) => selectedHitIds.includes(item.id));
                const someSelected = groupHits.some((item) => selectedHitIds.includes(item.id));
                return (
                  <section key={family} className="border-b border-[var(--color-border-1)] pb-4 last:border-b-0">
                    <div className="mb-3 flex items-center gap-3">
                      <Checkbox
                        checked={allSelected}
                        indeterminate={!allSelected && someSelected}
                        onChange={(event) => toggleGroup(groupHits, event.target.checked)}
                      />
                      <div className="text-[15px] font-medium text-[var(--color-text-1)]">
                        {familyLabel(family)}
                        <span className="ml-2 text-sm font-normal text-[var(--color-text-3)]">
                          {groupHits.length}
                        </span>
                      </div>
                    </div>
                    <div className="flex flex-col gap-3">
                      {groupHits.map((hit) => {
                        const facts = renderHitFacts(hit).filter((item) => displayValue(item.value) !== '--');
                        return (
                          <div
                            key={hit.id}
                            className="flex gap-3 rounded-md bg-[var(--color-fill-2)] px-3 py-3"
                          >
                            <Checkbox
                              className="mt-1"
                              checked={selectedHitIds.includes(hit.id)}
                              onChange={(event) => toggleHit(hit.id, event.target.checked)}
                            />
                            <div className="min-w-0 flex-1">
                              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                                <span className="text-base font-medium text-[var(--color-text-1)]">{hit.host}</span>
                                <span className="text-sm text-[var(--color-text-3)]">
                                  {hit.credential_label || hit.credential_id || '--'}
                                </span>
                                {hit.cmdb_model_id ? (
                                  <Tag className="m-0">{hit.cmdb_model_id}</Tag>
                                ) : null}
                              </div>
                              <div className="mt-2 grid grid-cols-1 gap-x-6 gap-y-1 sm:grid-cols-2 lg:grid-cols-3">
                                {facts.length ? (
                                  facts.map((fact) => (
                                    <div key={fact.label} className="text-sm text-[var(--color-text-2)]">
                                      <span className="text-[var(--color-text-3)]">{fact.label}: </span>
                                      {displayValue(fact.value)}
                                    </div>
                                  ))
                                ) : (
                                  <div className="text-sm text-[var(--color-text-3)]">{t('Scan.awaitingFacts')}</div>
                                )}
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </section>
                );
              })
            )}
          </div>
          {hitTotal > hits.length ? (
            <div className="mt-4 flex justify-end">
              <Button
                type="link"
                loading={hitsLoadingMore}
                disabled={hitsLoading || hitPage * HIT_PAGE_SIZE >= hitTotal}
                onClick={() => activeExecution && fetchHits(activeExecution.id, hitPage + 1)}
              >
                {t('Scan.loadMore')}
              </Button>
            </div>
          ) : null}
        </Spin>
      </Drawer>
    </div>
  );
};

export default ScanPage;
