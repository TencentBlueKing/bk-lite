'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Button, Drawer, Empty, Popconfirm, Select, Space, Tag, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import MarkdownIt from 'markdown-it';
import DOMPurify from 'dompurify';
import CustomTable from '@/components/custom-table';
import { useTranslation } from '@/utils/i18n';
import { useWikiApi } from '@/app/opspilot/api/wiki';
import { CheckItem } from '@/app/opspilot/types/wiki';

const md = new MarkdownIt({ html: false, linkify: true, breaks: true });
const mdHtml = (body: string) => ({ __html: DOMPurify.sanitize(md.render(body || '')) });
const MD_CLS =
  'text-sm leading-7 break-words [&_h1]:text-base [&_h2]:text-[15px] [&_h3]:text-sm [&_h1]:font-semibold [&_h2]:font-semibold [&_h3]:font-medium [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5 [&_code]:rounded [&_code]:bg-[var(--color-fill-1)] [&_code]:px-1';

const STATUS_COLOR: Record<string, string> = {
  open: 'gold',
  resolved: 'green',
  dismissed: 'default',
};

const CHECK_STATUS_KEY: Record<string, string> = {
  open: 'wiki.checkStatusOpen',
  resolved: 'wiki.checkStatusResolved',
  dismissed: 'wiki.checkStatusDismissed',
};

// 检查类型本地化(spec 4.5)
const CHECK_TYPE_KEY: Record<string, string> = {
  ambiguous_link: 'wiki.checkAmbiguousLink',
  conflict: 'wiki.checkConflict',
  duplicate: 'wiki.checkDuplicate',
  stale: 'wiki.checkStale',
  orphan: 'wiki.checkOrphan',
  broken_relation: 'wiki.checkBrokenRelation',
  no_source: 'wiki.checkNoSource',
  all_sources_invalid: 'wiki.checkAllSourcesInvalid',
  low_confidence: 'wiki.checkLowConfidence',
  cannot_merge: 'wiki.checkCannotMerge',
  bridge_node: 'wiki.checkBridgeNode',
  sparse_community: 'wiki.checkSparseCommunity',
  cross_community_edge: 'wiki.checkCrossCommunityEdge',
  schema_violation: 'wiki.checkSchemaViolation',
  missing: 'wiki.checkMissing',
  material_update: 'wiki.checkMaterialUpdate',
  source_invalid: 'wiki.checkSourceInvalid',
};

const CheckTab: React.FC<{ kbId: number }> = ({ kbId }) => {
  const { t } = useTranslation();
  const {
    fetchCheckItems,
    acceptCheck,
    rejectCheck,
    mergeDuplicateCheck,
    resolveCheck,
    batchAcceptChecks,
    batchRejectChecks,
    batchResolveChecks,
    scan,
  } = useWikiApi();
  const [data, setData] = useState<CheckItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [total, setTotal] = useState(0);
  const [statusFilter, setStatusFilter] = useState('open');
  const [checkTypeFilter, setCheckTypeFilter] = useState('');
  const [scanning, setScanning] = useState(false);
  const [batchSubmitting, setBatchSubmitting] = useState<'accept' | 'reject' | 'resolve' | null>(null);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [detail, setDetail] = useState<CheckItem | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchCheckItems(kbId, {
        page,
        page_size: pageSize,
        status: statusFilter || undefined,
        check_type: checkTypeFilter || undefined,
      });
      setData(res.items);
      setTotal(res.count);
      const openIds = new Set(res.items.filter((item) => item.status === 'open').map((item) => item.id));
      setSelectedRowKeys((keys) => keys.filter((key) => openIds.has(Number(key))));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId, page, pageSize, statusFilter, checkTypeFilter]);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId, page, pageSize, statusFilter, checkTypeFilter]);

  const statusOptions = useMemo(
    () => [
      { value: '', label: t('wiki.checkStatusAll') },
      { value: 'open', label: t('wiki.checkStatusOpen') },
      { value: 'resolved', label: t('wiki.checkStatusResolved') },
      { value: 'dismissed', label: t('wiki.checkStatusDismissed') },
    ],
    [t]
  );
  const checkTypeOptions = useMemo(
    () => [
      { value: '', label: t('wiki.checkTypeAll') },
      ...Object.entries(CHECK_TYPE_KEY).map(([value, labelKey]) => ({ value, label: t(labelKey) })),
    ],
    [t]
  );

  const resetSelectionAndPage = () => {
    setSelectedRowKeys([]);
    setPage(1);
  };

  const handleStatusFilterChange = (value: string) => {
    setStatusFilter(value);
    resetSelectionAndPage();
  };

  const handleCheckTypeFilterChange = (value: string) => {
    setCheckTypeFilter(value);
    resetSelectionAndPage();
  };

  const handleScan = async () => {
    setScanning(true);
    try {
      await scan(kbId);
      message.success(t('wiki.saveSuccess'));
      load();
    } finally {
      setScanning(false);
    }
  };

  const act = async (fn: () => Promise<unknown>) => {
    await fn();
    message.success(t('wiki.saveSuccess'));
    setDetail(null);
    load();
  };

  const typeLabel = (ct: string) => (CHECK_TYPE_KEY[ct] ? t(CHECK_TYPE_KEY[ct]) : ct);
  const statusLabel = (status: string) => (CHECK_STATUS_KEY[status] ? t(CHECK_STATUS_KEY[status]) : status);
  const resolutionOf = (item?: CheckItem | null) =>
    item?.related?.resolution as
      | {
          action?: string;
          operator?: string;
          note?: string;
          processed_at?: string;
        }
      | undefined;
  const canMergeDuplicate = (r: CheckItem) =>
    r.status === 'open' && r.check_type === 'duplicate' && !r.candidate_version && (r.related_pages?.length || 0) > 1;
  const selectedOpenItems = useMemo(() => {
    const selectedIds = new Set(selectedRowKeys.map((key) => Number(key)));
    return data.filter((item) => item.status === 'open' && selectedIds.has(item.id));
  }, [data, selectedRowKeys]);
  const selectedOpenIds = selectedOpenItems.map((item) => item.id);
  const hasSelectedOpenItems = selectedOpenIds.length > 0;
  const hasSelectedResolvableItems = selectedOpenItems.some((item) => !item.candidate_version);

  const batchMessage = (acceptedOrRejected: number, skipped: number) =>
    `${t('wiki.batchActionDone')}: ${t('wiki.processed')} ${acceptedOrRejected}, ${t('wiki.skipped')} ${skipped}`;

  const handleBatchAccept = async () => {
    if (!hasSelectedOpenItems) return;
    setBatchSubmitting('accept');
    try {
      const res = await batchAcceptChecks(selectedOpenIds);
      message.success(batchMessage(res.accepted, res.skipped));
      setSelectedRowKeys([]);
      load();
    } finally {
      setBatchSubmitting(null);
    }
  };

  const handleBatchReject = async () => {
    if (!hasSelectedOpenItems) return;
    setBatchSubmitting('reject');
    try {
      const res = await batchRejectChecks(selectedOpenIds);
      message.success(batchMessage(res.rejected, res.skipped));
      setSelectedRowKeys([]);
      load();
    } finally {
      setBatchSubmitting(null);
    }
  };

  const handleBatchResolve = async () => {
    if (!hasSelectedResolvableItems) return;
    setBatchSubmitting('resolve');
    try {
      const res = await batchResolveChecks(selectedOpenIds);
      message.success(batchMessage(res.resolved, res.skipped));
      setSelectedRowKeys([]);
      load();
    } finally {
      setBatchSubmitting(null);
    }
  };

  const columns: ColumnsType<CheckItem> = [
    {
      title: t('wiki.type'),
      dataIndex: 'check_type',
      key: 'check_type',
      width: 160,
      render: (ct: string) => typeLabel(ct),
    },
    {
      title: t('wiki.status'),
      dataIndex: 'status',
      key: 'status',
      width: 110,
      render: (s: string) => <Tag color={STATUS_COLOR[s] || 'default'}>{statusLabel(s)}</Tag>,
    },
    {
      title: t('wiki.related'),
      key: 'related',
      render: (_: unknown, r) => {
        const pages = r.related_pages || [];
        if (!pages.length) return <span className="text-xs text-[var(--color-text-3)]">--</span>;
        // 列出涉及页面标题(同标题重复时会一致),点「详情」看实际内容/对比
        return <span className="text-[var(--color-text-2)]">{pages.map((p) => p.title).join('  ·  ')}</span>;
      },
    },
    {
      title: t('common.actions'),
      key: 'action',
      width: 200,
      render: (_: unknown, r) => (
        <Space size={4}>
          <Button type="link" size="small" onClick={() => setDetail(r)}>
            {t('wiki.detail')}
          </Button>
          {r.status === 'open' &&
            (r.candidate_version ? (
              // 候选类(资料更新等):可采纳候选版本或丢弃
              <>
                <Button type="link" size="small" onClick={() => act(() => acceptCheck(r.id))}>
                  {t('wiki.accept')}
                </Button>
                <Button type="link" size="small" danger onClick={() => act(() => rejectCheck(r.id))}>
                  {t('wiki.reject')}
                </Button>
              </>
            ) : (
              // 扫描类(重复/低置信等):无候选版本,仅能忽略(标记已处理)
              <>
                {canMergeDuplicate(r) && (
                  <Popconfirm
                    title={t('wiki.mergeDuplicateConfirm')}
                    okText={t('wiki.confirm')}
                    cancelText={t('common.cancel')}
                    onConfirm={() => act(() => mergeDuplicateCheck(r.id))}
                  >
                    <Button type="link" size="small">
                      {t('wiki.mergeDuplicate')}
                    </Button>
                  </Popconfirm>
                )}
                <Popconfirm
                  title={t('wiki.markResolvedConfirm')}
                  okText={t('wiki.confirm')}
                  cancelText={t('common.cancel')}
                  onConfirm={() => act(() => resolveCheck(r.id))}
                >
                  <Button type="link" size="small">
                    {t('wiki.markResolved')}
                  </Button>
                </Popconfirm>
                <Button type="link" size="small" onClick={() => act(() => rejectCheck(r.id))}>
                  {t('wiki.dismiss')}
                </Button>
              </>
            ))}
        </Space>
      ),
    },
  ];

  const pages = detail?.related_pages || [];
  const resolution = resolutionOf(detail);
  const suggestedQueries = Array.isArray(detail?.related?.suggested_queries)
    ? (detail.related.suggested_queries as string[])
    : [];

  return (
    <div className="h-full flex flex-col">
      <div className="mb-3 flex shrink-0 flex-wrap items-center justify-between gap-2">
        <Space size={8} wrap>
          <span className="text-xs text-[var(--color-text-3)]">{t('wiki.filterStatus')}</span>
          <Select
            value={statusFilter}
            options={statusOptions}
            className="min-w-[132px]"
            onChange={handleStatusFilterChange}
          />
          <span className="text-xs text-[var(--color-text-3)]">{t('wiki.filterType')}</span>
          <Select
            value={checkTypeFilter}
            options={checkTypeOptions}
            className="min-w-[160px]"
            onChange={handleCheckTypeFilterChange}
          />
          <Tag className="m-0">
            {t('wiki.selected')}: {selectedRowKeys.length}
          </Tag>
          <Popconfirm
            title={t('wiki.batchAcceptConfirm')}
            okText={t('wiki.confirm')}
            cancelText={t('common.cancel')}
            disabled={!hasSelectedOpenItems}
            onConfirm={handleBatchAccept}
          >
            <Button disabled={!hasSelectedOpenItems} loading={batchSubmitting === 'accept'}>
              {t('wiki.batchAccept')}
            </Button>
          </Popconfirm>
          <Popconfirm
            title={t('wiki.batchRejectConfirm')}
            okText={t('wiki.confirm')}
            cancelText={t('common.cancel')}
            disabled={!hasSelectedOpenItems}
            onConfirm={handleBatchReject}
          >
            <Button danger disabled={!hasSelectedOpenItems} loading={batchSubmitting === 'reject'}>
              {t('wiki.batchReject')}
            </Button>
          </Popconfirm>
          <Popconfirm
            title={t('wiki.batchResolveConfirm')}
            okText={t('wiki.confirm')}
            cancelText={t('common.cancel')}
            disabled={!hasSelectedResolvableItems}
            onConfirm={handleBatchResolve}
          >
            <Button disabled={!hasSelectedResolvableItems} loading={batchSubmitting === 'resolve'}>
              {t('wiki.batchResolve')}
            </Button>
          </Popconfirm>
        </Space>
        <Button onClick={handleScan} loading={scanning}>
          {t('wiki.scan')}
        </Button>
      </div>
      {/* flex-1 容器给表格确定高度,使分页时 CustomTable 自动算出的 scroll.y 稳定 */}
      <div className="flex-1 min-h-0">
        <CustomTable<CheckItem>
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={data}
          rowSelection={{
            selectedRowKeys,
            onChange: setSelectedRowKeys,
            getCheckboxProps: (record) => ({ disabled: record.status !== 'open' }),
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

      {/* 检查详情:候选类展示「当前 vs 候选」对比,扫描类展示涉及页面内容 */}
      <Drawer
        title={detail ? typeLabel(detail.check_type) : ''}
        open={!!detail}
        width={760}
        onClose={() => setDetail(null)}
        destroyOnHidden
      >
        {detail &&
          (detail.candidate ? (
            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="mb-2 text-xs font-medium text-[var(--color-text-3)]">{t('wiki.currentVersion')}</div>
                <div className={MD_CLS} dangerouslySetInnerHTML={mdHtml(pages[0]?.body || '')} />
              </div>
              <div className="border-l border-[var(--color-border-2)] pl-4">
                <div className="mb-2 text-xs font-medium text-[var(--color-primary)]">{t('wiki.candidateVersion')}</div>
                <div className={MD_CLS} dangerouslySetInnerHTML={mdHtml(detail.candidate.body)} />
              </div>
            </div>
          ) : pages.length ? (
            <div className="space-y-4">
              {resolution && (
                <div className="rounded-lg border border-[var(--color-border-2)] bg-[var(--color-fill-1)] p-3">
                  <div className="mb-2 text-xs font-medium text-[var(--color-text-2)]">
                    {t('wiki.resolutionResult')}
                  </div>
                  <div className="space-y-1 text-xs text-[var(--color-text-3)]">
                    <div>
                      {t('wiki.operator')}: {resolution.operator || '--'}
                    </div>
                    <div>
                      {t('wiki.time')}: {resolution.processed_at || '--'}
                    </div>
                    {resolution.note && <div>{resolution.note}</div>}
                  </div>
                </div>
              )}
              {suggestedQueries.length > 0 && (
                <div>
                  <div className="mb-2 text-xs font-medium text-[var(--color-text-3)]">
                    {t('wiki.suggestedQueries')}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {suggestedQueries.map((query) => (
                      <Tag key={query} className="m-0">
                        {query}
                      </Tag>
                    ))}
                  </div>
                </div>
              )}
              <div className="text-xs text-[var(--color-text-3)]">{t('wiki.involvedPages')}</div>
              {pages.map((p) => (
                <div key={p.id} className="rounded-lg border border-[var(--color-border-2)] p-3">
                  <div className="mb-2 flex items-center gap-2 font-medium text-[var(--color-text-1)]">
                    {p.title}
                    <Tag className="m-0">{p.page_type}</Tag>
                  </div>
                  {p.body ? (
                    <div className={MD_CLS} dangerouslySetInnerHTML={mdHtml(p.body)} />
                  ) : (
                    <span className="text-xs text-[var(--color-text-3)]">--</span>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <Empty />
          ))}
      </Drawer>
    </div>
  );
};

export default CheckTab;
