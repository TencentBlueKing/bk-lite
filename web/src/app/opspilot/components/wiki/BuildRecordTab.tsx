'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Button, Descriptions, Drawer, Popconfirm, Select, Space, Tag, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import CustomTable from '@/components/custom-table';
import { useTranslation } from '@/utils/i18n';
import { useWikiApi } from '@/app/opspilot/api/wiki';
import type {
  BuildAffectedPage,
  BuildMaintenance,
  BuildMaintenanceStage,
  BuildPageAction,
  BuildRecord,
  BuildSourceChunk,
  BuildSourceMaterialTrace,
  BuildSourceTrace,
} from '@/app/opspilot/types/wiki';
import { TRIGGER_LABEL, STAGE_LABEL, BUILD_STATUS_LABEL, PAGE_STATUS_LABEL, formatWikiTime } from './wikiFormat';

const STATUS_COLOR: Record<string, string> = {
  success: 'green',
  running: 'processing',
  partial: 'gold',
  failed: 'red',
  cancelled: 'default',
};

const PAGE_STATUS_COLOR: Record<string, string> = { active: 'green', archived: 'default', source_invalid: 'red' };

const AFFECTED_PAGES_MAX_HEIGHT = 'calc(100vh - 400px)';
const SOURCE_TRACE_MAX_HEIGHT = 'calc(100vh - 460px)';

const MAINTENANCE_STAGE_LABEL: Record<string, string> = {
  relations: 'wiki.maintenanceRelations',
  page_embedding: 'wiki.maintenancePageEmbedding',
  chunk_embedding: 'wiki.maintenanceChunkEmbedding',
  check_sweep: 'wiki.maintenanceCheckSweep',
  deleted_page_prune: 'wiki.maintenanceDeletedPagePrune',
};

const MAINTENANCE_STATUS_LABEL: Record<string, string> = {
  success: 'wiki.maintenanceSuccess',
  partial: 'wiki.maintenancePartial',
  failed: 'wiki.maintenanceFailed',
  skipped: 'wiki.maintenanceSkipped',
};

const MAINTENANCE_STATUS_COLOR: Record<string, string> = {
  success: 'green',
  partial: 'gold',
  failed: 'red',
  skipped: 'default',
};

const MAINTENANCE_REASON_LABEL: Record<string, string> = {
  prune_deleted_pages_disabled: 'wiki.maintenancePruneDisabled',
};

const RETRYABLE_MAINTENANCE_STATUS = new Set(['partial', 'failed']);

// 计数键 → 中文标签 + 配色(避免直接暴露 {"new":0,...} 这类 JSON,用户看不懂)
const COUNT_META: Record<string, { key: string; color: string }> = {
  new: { key: 'wiki.countNew', color: 'green' },
  updated: { key: 'wiki.countUpdated', color: 'blue' },
  unchanged: { key: 'wiki.countUnchanged', color: 'default' },
  pending_review: { key: 'wiki.countPendingReview', color: 'gold' },
};

const ACTION_META: Record<string, { key: string; color: string }> = {
  new: { key: 'wiki.countNew', color: 'green' },
  updated: { key: 'wiki.countUpdated', color: 'blue' },
  unchanged: { key: 'wiki.countUnchanged', color: 'default' },
  pending_review: { key: 'wiki.countPendingReview', color: 'gold' },
};

// 构建记录工作区(spec 4.4):长期记录 + 详情(输入版本/受影响页/错误)+ 重试/继续/取消/查看结果
const BuildRecordTab: React.FC<{ kbId: number }> = ({ kbId }) => {
  const { t } = useTranslation();
  const { fetchBuildRecords, fetchBuildRecord, retryBuild, retryBuildMaintenance, batchRetryBuildMaintenance, cancelBuild } = useWikiApi();
  const [data, setData] = useState<BuildRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [total, setTotal] = useState(0);
  const [detail, setDetail] = useState<BuildRecord | null>(null);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [batchMaintenanceRetrying, setBatchMaintenanceRetrying] = useState(false);
  const [statusFilter, setStatusFilter] = useState('');
  const [triggerFilter, setTriggerFilter] = useState('');
  const [maintenanceStatusFilter, setMaintenanceStatusFilter] = useState('');
  const [maintenanceStageFilter, setMaintenanceStageFilter] = useState('');
  const [maintenanceStageStatusFilter, setMaintenanceStageStatusFilter] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchBuildRecords(kbId, {
        page,
        page_size: pageSize,
        status: statusFilter || undefined,
        trigger: triggerFilter || undefined,
        maintenance_status: maintenanceStatusFilter || undefined,
        maintenance_stage: maintenanceStageFilter || undefined,
        maintenance_stage_status: maintenanceStageStatusFilter || undefined,
      });
      setData(res.items);
      setTotal(res.count);
      const visibleIds = new Set(res.items.map((item) => item.id));
      setSelectedRowKeys((keys) => keys.filter((key) => visibleIds.has(Number(key))));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId, page, pageSize, statusFilter, triggerFilter, maintenanceStatusFilter, maintenanceStageFilter, maintenanceStageStatusFilter]);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId, page, pageSize, statusFilter, triggerFilter, maintenanceStatusFilter, maintenanceStageFilter, maintenanceStageStatusFilter]);

  // 有 running 记录时每 3s 轮询刷新进度,全部结束自动停止
  useEffect(() => {
    if (!data.some((b) => b.status === 'running')) return;
    const timer = setInterval(() => load(), 3000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  const openDetail = async (id: number) => setDetail(await fetchBuildRecord(id));
  const handleRetry = async (id: number) => {
    await retryBuild(id);
    message.success(t('wiki.saveSuccess'));
    load();
  };
  const handleMaintenanceRetry = async (id: number, stages?: string[]) => {
    const next = await retryBuildMaintenance(id, stages);
    message.success(t('wiki.maintenanceRetryDone'));
    setDetail((current) => (current?.id === id ? next : current));
    load();
  };
  const selectedRecordIds = useMemo(() => selectedRowKeys.map((key) => Number(key)), [selectedRowKeys]);
  const hasSelectedRecords = selectedRecordIds.length > 0;
  const handleBatchMaintenanceRetry = async () => {
    if (!hasSelectedRecords) return;
    setBatchMaintenanceRetrying(true);
    try {
      const stages = maintenanceStageFilter ? [maintenanceStageFilter] : undefined;
      const result = await batchRetryBuildMaintenance(kbId, selectedRecordIds, stages);
      message.success(`${t('wiki.batchRetryMaintenance')}: ${t('wiki.processed')} ${result.retried}, ${t('wiki.skipped')} ${result.skipped}`);
      setSelectedRowKeys([]);
      load();
    } finally {
      setBatchMaintenanceRetrying(false);
    }
  };
  const handleCancel = async (id: number) => {
    await cancelBuild(id);
    message.success(t('wiki.saveSuccess'));
    load();
  };
  const resetFilterPage = () => setPage(1);
  const handleStatusFilterChange = (value: string) => {
    setStatusFilter(value || '');
    resetFilterPage();
  };
  const handleTriggerFilterChange = (value: string) => {
    setTriggerFilter(value || '');
    resetFilterPage();
  };
  const handleMaintenanceStatusFilterChange = (value: string) => {
    setMaintenanceStatusFilter(value || '');
    resetFilterPage();
  };
  const handleMaintenanceStageFilterChange = (value: string) => {
    setMaintenanceStageFilter(value || '');
    resetFilterPage();
  };
  const handleMaintenanceStageStatusFilterChange = (value: string) => {
    setMaintenanceStageStatusFilter(value || '');
    resetFilterPage();
  };

  const canRetryMaintenance = (record: BuildRecord) =>
    RETRYABLE_MAINTENANCE_STATUS.has(record.maintenance?.status || '') && !!(record.affected_pages || []).length;
  const buildStatusOptions = useMemo(
    () => [
      { value: '', label: t('wiki.buildRecordStatusAll') },
      ...Object.entries(BUILD_STATUS_LABEL).map(([value, labelKey]) => ({ value, label: t(labelKey) })),
    ],
    [t]
  );
  const triggerOptions = useMemo(
    () => [
      { value: '', label: t('wiki.buildRecordTriggerAll') },
      ...Object.entries(TRIGGER_LABEL).map(([value, labelKey]) => ({ value, label: t(labelKey) })),
    ],
    [t]
  );
  const maintenanceStatusOptions = useMemo(
    () => [
      { value: '', label: t('wiki.maintenanceStatusAll') },
      ...Object.entries(MAINTENANCE_STATUS_LABEL).map(([value, labelKey]) => ({ value, label: t(labelKey) })),
    ],
    [t]
  );
  const maintenanceStageOptions = useMemo(
    () => [
      { value: '', label: t('wiki.maintenanceStageAll') },
      ...Object.entries(MAINTENANCE_STAGE_LABEL).map(([value, labelKey]) => ({ value, label: t(labelKey) })),
    ],
    [t]
  );
  const maintenanceStageStatusOptions = useMemo(
    () => [
      { value: '', label: t('wiki.maintenanceStageStatusAll') },
      ...Object.entries(MAINTENANCE_STATUS_LABEL).map(([value, labelKey]) => ({ value, label: t(labelKey) })),
    ],
    [t]
  );

  // 计数渲染:仅展示非零项为标签(新增 6 / 修改 3 …);全为 0 显示"无变更"
  const renderCounts = (c?: Record<string, number>) => {
    const entries = Object.entries(c || {}).filter(([, v]) => v);
    if (!entries.length) return <span className="text-[var(--color-text-4)]">{t('wiki.noChange')}</span>;
    return (
      <Space size={[4, 4]} wrap>
        {entries.map(([k, v]) => {
          const meta = COUNT_META[k];
          return (
            <Tag key={k} color={meta?.color || 'default'} className="m-0">
              {meta ? t(meta.key) : k} {v}
            </Tag>
          );
        })}
      </Space>
    );
  };

  const labelOf = (map: Record<string, string>, v: string) => (map[v] ? t(map[v]) : v || '--');

  const renderMaintenanceStage = (stageKey: string, stage: BuildMaintenanceStage) => {
    const status = stage.status || '';
    return (
      <div
        key={stageKey}
        className="min-w-0 rounded-md border border-[var(--color-border-2)] bg-[var(--color-fill-1)] px-2 py-1.5"
      >
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="break-words text-sm font-medium text-[var(--color-text-1)]">
            {labelOf(MAINTENANCE_STAGE_LABEL, stageKey)}
          </span>
          <Tag color={MAINTENANCE_STATUS_COLOR[status] || 'default'} className="m-0">
            {labelOf(MAINTENANCE_STATUS_LABEL, status)}
          </Tag>
          {typeof stage.count === 'number' && (
            <Tag className="m-0">
              {t('wiki.counts')} {stage.count}
            </Tag>
          )}
          {detail && stage.status === 'failed' && (
            <Button type="link" size="small" className="h-auto p-0" onClick={() => handleMaintenanceRetry(detail.id, [stageKey])}>
              {t('wiki.maintenanceRetryStage')}
            </Button>
          )}
        </div>
        {stage.reason && (
          <div className="mt-1 break-words text-xs text-[var(--color-text-3)]">
            {labelOf(MAINTENANCE_REASON_LABEL, stage.reason)}
          </div>
        )}
        {stage.error && <div className="mt-1 break-words text-xs text-red-500">{stage.error}</div>}
      </div>
    );
  };

  const renderMaintenance = (maintenance?: BuildMaintenance) => {
    const stages = Object.entries(maintenance?.stages || {});
    if (!maintenance || !stages.length) return <span className="text-[var(--color-text-4)]">--</span>;
    return (
      <div className="flex flex-col gap-2">
        <Space size={[4, 4]} wrap>
          {maintenance.status && (
            <Tag color={MAINTENANCE_STATUS_COLOR[maintenance.status] || 'default'} className="m-0">
              {labelOf(MAINTENANCE_STATUS_LABEL, maintenance.status)}
            </Tag>
          )}
          {maintenance.event && <Tag className="m-0">{labelOf(TRIGGER_LABEL, maintenance.event)}</Tag>}
        </Space>
        <div className="flex flex-col gap-1.5">
          {stages.map(([stageKey, stage]) => renderMaintenanceStage(stageKey, stage))}
        </div>
      </div>
    );
  };

  const renderAffectedPages = (pages?: BuildAffectedPage[], pageIds?: number[]) => {
    const existingPages = pages || [];
    if (existingPages.length) {
      return (
        <div className="flex flex-col gap-2 overflow-auto pr-1" style={{ maxHeight: AFFECTED_PAGES_MAX_HEIGHT }}>
          {existingPages.map((pageInfo) => (
            <div
              key={pageInfo.id}
              className="min-w-0 rounded-md border border-[var(--color-border-2)] bg-[var(--color-fill-1)] px-2 py-1.5"
            >
              <div className="break-words text-sm font-medium text-[var(--color-text-1)]">
                {pageInfo.title || `#${pageInfo.id}`}
              </div>
              <Space size={[4, 4]} wrap className="mt-1">
                <Tag className="m-0">#{pageInfo.id}</Tag>
                {pageInfo.page_type && <Tag className="m-0">{pageInfo.page_type}</Tag>}
                {pageInfo.status && (
                  <Tag color={PAGE_STATUS_COLOR[pageInfo.status] || 'default'} className="m-0">
                    {labelOf(PAGE_STATUS_LABEL, pageInfo.status)}
                  </Tag>
                )}
              </Space>
            </div>
          ))}
        </div>
      );
    }

    const fallbackPageIds = pageIds || [];
    if (!fallbackPageIds.length) return <span className="text-[var(--color-text-4)]">--</span>;
    return (
      <Space size={[4, 4]} wrap>
        {fallbackPageIds.map((pageId) => (
          <Tag key={pageId} className="m-0">
            #{pageId}
          </Tag>
        ))}
      </Space>
    );
  };

  const renderActionTag = (action: string) => {
    const meta = ACTION_META[action];
    return (
      <Tag color={meta?.color || 'default'} className="m-0">
        {meta ? t(meta.key) : action}
      </Tag>
    );
  };

  const renderSourceChunk = (chunk: BuildSourceChunk) => (
    <div
      key={chunk.index}
      className="min-w-0 rounded-md border border-[var(--color-border-2)] bg-[var(--color-fill-1)] px-2 py-1.5"
    >
      <Space size={[4, 4]} wrap>
        <Tag className="m-0">
          {t('wiki.sourceChunk')} #{chunk.index + 1}
        </Tag>
        <Tag className="m-0">
          {chunk.start}-{chunk.end}
        </Tag>
      </Space>
      <div className="mt-1 whitespace-pre-wrap break-words text-xs text-[var(--color-text-3)]">{chunk.preview || '--'}</div>
    </div>
  );

  const renderPageAction = (action: BuildPageAction, index: number) => {
    const locator = action.source_locator || {};
    return (
      <div
        key={`${action.page_id}-${action.action}-${index}`}
        className="min-w-0 rounded-md border border-[var(--color-border-2)] bg-[var(--color-fill-1)] px-2 py-1.5"
      >
        <div className="break-words text-sm font-medium text-[var(--color-text-1)]">
          {action.title || `#${action.page_id}`}
        </div>
        <Space size={[4, 4]} wrap className="mt-1">
          <Tag className="m-0">#{action.page_id}</Tag>
          {action.page_type && <Tag className="m-0">{action.page_type}</Tag>}
          {renderActionTag(action.action)}
          {typeof locator.chunk_index === 'number' && (
            <Tag className="m-0">
              {t('wiki.sourceChunk')} #{locator.chunk_index + 1}
            </Tag>
          )}
        </Space>
        {locator.snippet && (
          <div className="mt-1 whitespace-pre-wrap break-words text-xs text-[var(--color-text-3)]">{locator.snippet}</div>
        )}
      </div>
    );
  };

  const renderSourceTraceSections = (chunks: BuildSourceChunk[], pageActions: BuildPageAction[]) => (
    <>
      {!!pageActions.length && (
        <div className="flex flex-col gap-1.5">
          <div className="text-xs text-[var(--color-text-3)]">{t('wiki.pageActions')}</div>
          {pageActions.map(renderPageAction)}
        </div>
      )}
      {!!chunks.length && (
        <div className="flex flex-col gap-1.5">
          <div className="text-xs text-[var(--color-text-3)]">{t('wiki.sourceChunks')}</div>
          {chunks.map(renderSourceChunk)}
        </div>
      )}
    </>
  );

  const renderSourceMaterialTrace = (materialTrace: BuildSourceMaterialTrace) => (
    <div key={materialTrace.material_id} className="min-w-0 border-l-2 border-[var(--color-border-2)] pl-2">
      <Space size={[4, 4]} wrap>
        <Tag className="m-0">{t('wiki.sourceMaterial')}</Tag>
        <Tag className="m-0">#{materialTrace.material_id}</Tag>
        <span className="break-words text-sm font-medium text-[var(--color-text-1)]">{materialTrace.material_name}</span>
      </Space>
      <div className="mt-2 flex flex-col gap-2">
        {renderSourceTraceSections(materialTrace.chunks || [], materialTrace.page_actions || [])}
      </div>
    </div>
  );

  const renderSourceTrace = (trace?: BuildSourceTrace) => {
    const chunks = trace?.chunks || [];
    const pageActions = trace?.page_actions || [];
    const materials = trace?.materials || [];
    if (!chunks.length && !pageActions.length && !materials.length) return <span className="text-[var(--color-text-4)]">--</span>;
    return (
      <div className="flex flex-col gap-3 overflow-auto pr-1" style={{ maxHeight: SOURCE_TRACE_MAX_HEIGHT }}>
        {!!materials.length && (
          <div className="flex flex-col gap-1.5">
            <div className="text-xs text-[var(--color-text-3)]">{t('wiki.sourceMaterials')}</div>
            {materials.map(renderSourceMaterialTrace)}
          </div>
        )}
        {renderSourceTraceSections(chunks, pageActions)}
      </div>
    );
  };

  const columns: ColumnsType<BuildRecord> = [
    {
      title: t('wiki.trigger'),
      dataIndex: 'trigger',
      key: 'trigger',
      width: 120,
      render: (v: string) => labelOf(TRIGGER_LABEL, v),
    },
    {
      title: t('wiki.status'),
      dataIndex: 'status',
      key: 'status',
      width: 110,
      render: (s: string) => <Tag color={STATUS_COLOR[s] || 'default'}>{labelOf(BUILD_STATUS_LABEL, s)}</Tag>,
    },
    {
      title: t('wiki.stage'),
      dataIndex: 'stage',
      key: 'stage',
      width: 120,
      render: (v: string) => labelOf(STAGE_LABEL, v),
    },
    {
      title: t('wiki.counts'),
      dataIndex: 'counts',
      key: 'counts',
      render: (c: Record<string, number>) => renderCounts(c),
    },
    {
      title: t('wiki.time'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      render: (v: string) => formatWikiTime(v),
    },
    {
      title: t('common.actions'),
      key: 'action',
      width: 180,
      render: (_: unknown, r) => (
        <Space>
          <Button type="link" size="small" onClick={() => openDetail(r.id)}>
            {t('wiki.viewResult')}
          </Button>
          {['failed', 'partial', 'cancelled'].includes(r.status) && (
            <Button type="link" size="small" onClick={() => handleRetry(r.id)}>
              {t('wiki.retry')}
            </Button>
          )}
          {canRetryMaintenance(r) && (
            <Button type="link" size="small" onClick={() => handleMaintenanceRetry(r.id)}>
              {t('wiki.maintenanceRetry')}
            </Button>
          )}
          {r.status === 'running' && (
            <Popconfirm title={t('wiki.cancelConfirm')} onConfirm={() => handleCancel(r.id)}>
              <Button type="link" size="small" danger>
                {t('wiki.cancel')}
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    // h-full + flex:给表格一个确定高度的父级,使 CustomTable 开启分页时自动算出的 scroll.y 稳定(否则只显示 1 行)
    <div className="h-full flex flex-col">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="text-xs text-[var(--color-text-3)]">{t('wiki.filterStatus')}</span>
        <Select value={statusFilter} options={buildStatusOptions} className="min-w-[132px]" onChange={handleStatusFilterChange} />
        <span className="text-xs text-[var(--color-text-3)]">{t('wiki.trigger')}</span>
        <Select value={triggerFilter} options={triggerOptions} className="min-w-[132px]" onChange={handleTriggerFilterChange} />
        <span className="text-xs text-[var(--color-text-3)]">{t('wiki.maintenanceResult')}</span>
        <Select
          value={maintenanceStatusFilter}
          options={maintenanceStatusOptions}
          className="min-w-[132px]"
          onChange={handleMaintenanceStatusFilterChange}
        />
        <span className="text-xs text-[var(--color-text-3)]">{t('wiki.maintenanceStage')}</span>
        <Select
          value={maintenanceStageFilter}
          options={maintenanceStageOptions}
          className="min-w-[150px]"
          onChange={handleMaintenanceStageFilterChange}
        />
        <Select
          value={maintenanceStageStatusFilter}
          options={maintenanceStageStatusOptions}
          className="min-w-[132px]"
          onChange={handleMaintenanceStageStatusFilterChange}
        />
        <Tag className="m-0">
          {t('wiki.selected')}: {selectedRowKeys.length}
        </Tag>
        <Popconfirm
          title={t('wiki.batchRetryMaintenanceConfirm')}
          okText={t('common.confirm')}
          cancelText={t('common.cancel')}
          disabled={!hasSelectedRecords}
          onConfirm={handleBatchMaintenanceRetry}
        >
          <Button disabled={!hasSelectedRecords} loading={batchMaintenanceRetrying}>
            {t('wiki.batchRetryMaintenance')}
          </Button>
        </Popconfirm>
      </div>
      <div className="flex-1 min-h-0">
        <CustomTable<BuildRecord>
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={data}
          rowSelection={{
            selectedRowKeys,
            onChange: setSelectedRowKeys,
            getCheckboxProps: (record) => ({ disabled: !canRetryMaintenance(record) }),
          }}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            onChange: (p, ps) => {
              setPage(p);
              setPageSize(ps);
            },
          }}
          scroll={{ x: undefined }}
        />
      </div>
      <Drawer
        title={`${t('wiki.buildRecord')} #${detail?.id ?? ''}`}
        open={!!detail}
        width={560}
        onClose={() => setDetail(null)}
      >
        {detail && (
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label={t('wiki.trigger')}>{labelOf(TRIGGER_LABEL, detail.trigger)}</Descriptions.Item>
            <Descriptions.Item label={t('wiki.operator')}>{detail.operator || '--'}</Descriptions.Item>
            <Descriptions.Item label={t('wiki.inputMaterial')}>{detail.input_label || '--'}</Descriptions.Item>
            <Descriptions.Item label={t('wiki.sourceTrace')}>
              {renderSourceTrace(detail.inputs?.source_trace)}
            </Descriptions.Item>
            <Descriptions.Item label={t('wiki.stage')}>
              {labelOf(STAGE_LABEL, detail.stage)}({detail.progress ?? 0}%)
            </Descriptions.Item>
            <Descriptions.Item label={t('wiki.status')}>
              <Tag color={STATUS_COLOR[detail.status] || 'default'}>{labelOf(BUILD_STATUS_LABEL, detail.status)}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label={t('wiki.counts')}>{renderCounts(detail.counts)}</Descriptions.Item>
            <Descriptions.Item label={t('wiki.maintenanceResult')}>{renderMaintenance(detail.maintenance)}</Descriptions.Item>
            <Descriptions.Item label={t('wiki.affectedPages')}>
              {renderAffectedPages(detail.affected_page_details, detail.affected_pages)}
            </Descriptions.Item>
            <Descriptions.Item label={t('wiki.errors')}>{(detail.errors || []).join('; ') || '--'}</Descriptions.Item>
          </Descriptions>
        )}
      </Drawer>
    </div>
  );
};

export default BuildRecordTab;
