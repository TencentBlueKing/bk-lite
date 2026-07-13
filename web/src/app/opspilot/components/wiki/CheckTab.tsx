'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Button, Drawer, Input, Modal, Popconfirm, Select, Space, Tag, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import MarkdownIt from 'markdown-it';
import DOMPurify from 'dompurify';
import CustomTable from '@/components/custom-table';
import { useTranslation } from '@/utils/i18n';
import { useWikiApi } from '@/app/opspilot/api/wiki';
import { CheckItem, CheckDecisionAction } from '@/app/opspilot/types/wiki';

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
  surprise_link: 'wiki.checkSurpriseLink',
  schema_violation: 'wiki.checkSchemaViolation',
  schema_changed: 'wiki.checkSchemaChanged',
  missing: 'wiki.checkMissing',
  material_update: 'wiki.checkMaterialUpdate',
  source_invalid: 'wiki.checkSourceInvalid',
  qa_answer_candidate: 'wiki.checkQaAnswerCandidate',
};

// phase 7: 决策中心 - 按 check_type 路由
// 知识冲突 3 选 1
const KNOWLEDGE_CONFLICT_TYPES = new Set(['conflict', 'material_update', 'cannot_merge']);
// 页面合并 2 选 1
const PAGE_IDENTITY_TYPES = new Set(['duplicate']);

const CheckTab: React.FC<{ kbId: number }> = ({ kbId }) => {
  const { t } = useTranslation();
  const {
    fetchCheckItems,
    decideCheck,
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
  // phase 7.3: edit_accept 输入的编辑后正文
  const [editingItem, setEditingItem] = useState<CheckItem | null>(null);
  const [editBody, setEditBody] = useState('');
  const [submitting, setSubmitting] = useState<CheckDecisionAction | null>(null);
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
  // phase 7.2: 待办列表只显示知识冲突 / 页面合并,其他系统级(orphan / no_source 等)进独立过滤
  const decisionCheckTypes = useMemo(
    () => [
      { value: '', label: t('wiki.checkTypeAll') },
      ...Object.entries(CHECK_TYPE_KEY)
        .filter(([k]) => KNOWLEDGE_CONFLICT_TYPES.has(k) || PAGE_IDENTITY_TYPES.has(k))
        .map(([value, labelKey]) => ({ value, label: t(labelKey) })),
    ],
    [t]
  );

  const handleStatusFilterChange = (value: string) => {
    setStatusFilter(value);
    setPage(1);
  };

  const handleCheckTypeFilterChange = (value: string) => {
    setCheckTypeFilter(value);
    setPage(1);
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

  // phase 7.3 + 7.4: 语义化决策调用
  const handleDecide = async (item: CheckItem, action: CheckDecisionAction, body?: string) => {
    setSubmitting(action);
    try {
      const res = await decideCheck(item.id, { action, body });
      message.success(t('wiki.saveSuccess'));
      setDetail(null);
      setEditingItem(null);
      setEditBody('');
      console.info(`[decision-center] rule_id=${res.rule_id} action=${action}`);
      load();
    } catch (err) {
      message.error(String(err));
    } finally {
      setSubmitting(null);
    }
  };

  const openEditAcceptDialog = (item: CheckItem) => {
    setEditingItem(item);
    setEditBody(item.candidate?.body || '');
  };

  // phase 7.7: 已处理记录展示 - 包含规则状态 + 回放次数
  const renderResolution = (item: CheckItem) => {
    const resolution = item.related?.resolution as
      | {
          action?: string;
          operator?: string;
          processed_at?: string;
        }
      | undefined;
    if (!resolution) return null;
    return (
      <div className="mt-2 text-xs text-[var(--color-text-3)]">
        <span>{t('wiki.processed')}: {resolution.action}</span>
        {resolution.operator && <span className="ml-2">{t('wiki.operator')}: {resolution.operator}</span>}
        {resolution.processed_at && (
          <span className="ml-2">{t('wiki.detail')}: {resolution.processed_at}</span>
        )}
        {item.decision_key && (
          <div className="mt-1">decision_key: {item.decision_key.substring(0, 12)}...</div>
        )}
      </div>
    );
  };

  // phase 7.3 + 7.4: 决策按钮按 check_type 路由
  const renderDecisionButtons = (item: CheckItem) => {
    if (item.status !== 'open') return null;
    if (KNOWLEDGE_CONFLICT_TYPES.has(item.check_type)) {
      return (
        <Space size={4} wrap>
          <Button
            type="primary"
            size="small"
            loading={submitting === 'keep_current'}
            onClick={() => handleDecide(item, 'keep_current')}
          >
            {t('wiki.decisionKeepCurrent')}
          </Button>
          <Button
            type="primary"
            size="small"
            loading={submitting === 'use_new'}
            onClick={() => handleDecide(item, 'use_new')}
          >
            {t('wiki.decisionUseNew')}
          </Button>
          <Button
            size="small"
            loading={submitting === 'edit_accept'}
            onClick={() => openEditAcceptDialog(item)}
          >
            {t('wiki.decisionEditAccept')}
          </Button>
        </Space>
      );
    }
    if (PAGE_IDENTITY_TYPES.has(item.check_type)) {
      return (
        <Space size={4} wrap>
          <Button
            type="primary"
            size="small"
            loading={submitting === 'keep_separate'}
            onClick={() => handleDecide(item, 'keep_separate')}
          >
            {t('wiki.decisionKeepSeparate')}
          </Button>
          <Button
            type="primary"
            size="small"
            loading={submitting === 'merge'}
            onClick={() => handleDecide(item, 'merge')}
          >
            {t('wiki.decisionMerge')}
          </Button>
        </Space>
      );
    }
    return null;
  };

  const typeLabel = (ct: string) => (CHECK_TYPE_KEY[ct] ? t(CHECK_TYPE_KEY[ct]) : ct);
  const statusLabel = (status: string) => (CHECK_STATUS_KEY[status] ? t(CHECK_STATUS_KEY[status]) : status);

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
        return <span className="text-[var(--color-text-2)]">{pages.map((p) => p.title).join('  ·  ')}</span>;
      },
    },
    {
      title: t('common.actions'),
      key: 'action',
      width: 380,
      render: (_: unknown, r) => (
        <Space size={4} wrap>
          <Button type="link" size="small" onClick={() => setDetail(r)}>
            {t('wiki.detail')}
          </Button>
          {renderDecisionButtons(r)}
        </Space>
      ),
    },
  ];

  const pages = detail?.related_pages || [];
  const suggestedQueries = Array.isArray(detail?.related?.suggested_queries)
    ? (detail.related.suggested_queries as string[])
    : [];

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Select
          value={statusFilter}
          onChange={handleStatusFilterChange}
          options={statusOptions}
          style={{ width: 160 }}
          placeholder={t('wiki.checkStatusAll')}
        />
        <Select
          value={checkTypeFilter}
          onChange={handleCheckTypeFilterChange}
          options={decisionCheckTypes}
          style={{ width: 220 }}
          showSearch
          placeholder={t('wiki.checkTypeAll')}
        />
        <Popconfirm
          title={t('wiki.scanConfirm')}
          onConfirm={handleScan}
          okText={t('common.confirm')}
          cancelText={t('common.cancel')}
        >
          <Button loading={scanning}>{t('wiki.scan')}</Button>
        </Popconfirm>
      </div>

      <CustomTable<CheckItem>
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={data}
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
        onRow={(record) => ({
          onClick: () => setDetail(record),
        })}
      />

      {/* 详情 Drawer */}
      <Drawer
        title={`${t('wiki.detail')}: ${typeLabel(detail?.check_type || '')}`}
        open={!!detail}
        width={720}
        onClose={() => setDetail(null)}
        destroyOnHidden
      >
        {detail && (
          <div className="space-y-4">
            {pages.length > 0 && (
              <div>
                <div className="mb-2 text-sm font-medium">{t('wiki.involvedPages')}</div>
                <div className="flex flex-wrap gap-2">
                  {pages.map((p) => (
                    <Tag key={p.id} color="geekblue">{p.title}</Tag>
                  ))}
                </div>
              </div>
            )}

            {detail.related?.materials && (
              <div>
                <div className="mb-2 text-sm font-medium">{t('wiki.sourceMaterials')}</div>
                <div className="flex flex-wrap gap-2">
                  {(detail.related.materials as Array<{ id: number; name?: string }>).map((m) => (
                    <Tag key={m.id}>{m.name || `#${m.id}`}</Tag>
                  ))}
                </div>
              </div>
            )}

            {detail.candidate && (
              <div>
                <div className="mb-2 text-sm font-medium">{t('wiki.candidate')}</div>
                <div className="rounded border bg-[var(--color-bg-1)] p-3">
                  <div
                    className={MD_CLS}
                    dangerouslySetInnerHTML={mdHtml(detail.candidate.body)}
                  />
                </div>
              </div>
            )}

            {/* phase 7.3 / 7.4: 决策按钮在 Drawer 内 */}
            <div className="rounded border bg-[var(--color-fill-1)] p-3">
              <div className="mb-2 text-sm font-medium">{t('wiki.decision')}</div>
              {renderDecisionButtons(detail)}
            </div>

            {/* phase 7.7: 已处理记录展示 */}
            {renderResolution(detail)}

            {suggestedQueries.length > 0 && (
              <div>
                <div className="mb-2 text-sm font-medium">{t('wiki.suggestedQueries')}</div>
                <div className="flex flex-wrap gap-2">
                  {suggestedQueries.map((q) => (
                    <Tag key={q}>{q}</Tag>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </Drawer>

      {/* phase 7.3: edit_accept 弹 Modal 接收新正文 */}
      <Modal
        title={t('wiki.decisionEditAcceptTitle')}
        open={!!editingItem}
        width={720}
        onCancel={() => {
          setEditingItem(null);
          setEditBody('');
        }}
        onOk={() => {
          if (editingItem && editBody.trim()) {
            handleDecide(editingItem, 'edit_accept', editBody);
          }
        }}
        okButtonProps={{ disabled: !editBody.trim() || submitting === 'edit_accept' }}
        okText={t('wiki.decisionEditAccept')}
        cancelText={t('common.cancel')}
      >
        <div className="mb-2 text-sm text-[var(--color-text-3)]">
          {t('wiki.decisionEditAcceptTip')}
        </div>
        {editingItem?.candidate && (
          <div className="mb-3 rounded border bg-[var(--color-bg-1)] p-3">
            <div className="mb-1 text-xs text-[var(--color-text-3)]">
              {t('wiki.candidate')}:
            </div>
            <div className="max-h-32 overflow-auto text-xs" dangerouslySetInnerHTML={mdHtml(editingItem.candidate.body)} />
          </div>
        )}
        <Input.TextArea
          value={editBody}
          onChange={(e) => setEditBody(e.target.value)}
          autoSize={{ minRows: 10, maxRows: 20 }}
          placeholder={t('wiki.decisionEditAcceptPlaceholder')}
        />
      </Modal>
    </div>
  );
};

export default CheckTab;