'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Button,
  Input,
  message,
  Pagination,
  Popconfirm,
  Select,
  Space,
  Spin,
  Tabs,
  Tag,
  Tooltip,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { DownOutlined, ExportOutlined, ReloadOutlined } from '@ant-design/icons';

import OperateDrawer from '@/components/operate-drawer';
import CustomTable from '@/components/custom-table';
import CompactEmptyState from '@/components/compact-empty-state';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import FilterToolbar from '@/components/filter-toolbar';
import PermissionWrapper from '@/components/permission';
import ComplianceTag from '@/app/patch-manager/components/compliance-tag';
import SeverityTag from '@/app/patch-manager/components/severity-tag';
import usePatchManagerApi from '@/app/patch-manager/api';
import type {
  BaselineComplianceDetailsResponse,
  BaselineComplianceDistribution,
  BaselineComplianceHostDetail,
  BaselineComplianceHostObject,
  BaselineComplianceObjectsResponse,
  BaselineCompliancePatchDetail,
  BaselineCompliancePatchObject,
  BaselineCompliancePerspective,
  BaselineComplianceResultStatus,
} from '@/app/patch-manager/types';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { useTranslation } from '@/utils/i18n';
import {
  formatComplianceEvidence,
  getComplianceObjectBorderColor,
  getComplianceResultPresentation,
} from './presentation';
import {
  buildBaselineComplianceWorkbook,
  downloadBaselineComplianceWorkbook,
  sanitizeExportFilename,
} from './export';
import styles from './index.module.scss';

interface BaselineSummary {
  id: number;
  name: string;
  bound_host_count?: number;
  can_assess?: boolean;
  assess_disabled_reason?: string;
}

interface BaselineComplianceDetailProps {
  open: boolean;
  baseline: BaselineSummary | null;
  onClose: () => void;
  onRefresh?: () => void | Promise<void>;
}

type ComplianceDetailSource = BaselineComplianceHostDetail | BaselineCompliancePatchDetail;
type ComplianceDetailRow = ComplianceDetailSource & {
  evidence_display: string;
  reason_display: string;
  evaluated_at_display: string;
};

function ResultTag({ status }: { status: BaselineComplianceResultStatus }) {
  const { t } = useTranslation();
  const presentation = getComplianceResultPresentation(status, 'requirement');
  return (
    <Tag color={presentation.color} style={{ marginInlineEnd: 0 }}>
      {t(presentation.labelKey)}
    </Tag>
  );
}

function DistributionTags({ items }: { items: BaselineComplianceDistribution[] }) {
  const { t } = useTranslation();
  if (!items.length) return null;
  return (
    <Space size={[4, 4]} wrap>
      {items.map((item) => {
        const presentation = getComplianceResultPresentation(item.status, 'requirement');
        return (
          <Tag key={item.status} color={presentation.color} style={{ marginInlineEnd: 0 }}>
            {t(presentation.labelKey)} {item.count}
          </Tag>
        );
      })}
    </Space>
  );
}

export default function BaselineComplianceDetail({
  open,
  baseline,
  onClose,
  onRefresh,
}: BaselineComplianceDetailProps) {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const api = usePatchManagerApi();
  const apiRef = useRef(api);
  apiRef.current = api;
  const onRefreshRef = useRef(onRefresh);
  onRefreshRef.current = onRefresh;
  const [perspective, setPerspective] = useState<BaselineCompliancePerspective>('host');
  const [objectsData, setObjectsData] = useState<BaselineComplianceObjectsResponse | null>(null);
  const [detailsData, setDetailsData] = useState<BaselineComplianceDetailsResponse | null>(null);
  const [objectsLoading, setObjectsLoading] = useState(false);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [assessing, setAssessing] = useState(false);
  const [objectSearch, setObjectSearch] = useState('');
  const [detailSearch, setDetailSearch] = useState('');
  const [appliedDetailSearch, setAppliedDetailSearch] = useState('');
  const [detailStatus, setDetailStatus] = useState<BaselineComplianceResultStatus>();
  const [selectedId, setSelectedId] = useState<number>();
  const [detailPage, setDetailPage] = useState(1);
  const [detailPageSize, setDetailPageSize] = useState(20);
  const [selectedDetailKeys, setSelectedDetailKeys] = useState<React.Key[]>([]);
  const selectedIdRef = useRef<number | undefined>(undefined);
  selectedIdRef.current = selectedId;
  const objectsRequestRef = useRef<AbortController | null>(null);
  const detailsRequestRef = useRef<AbortController | null>(null);
  const objectsRequestKeyRef = useRef('');
  const detailsRequestKeyRef = useRef('');
  const objectsGenerationRef = useRef(0);
  const detailsGenerationRef = useRef(0);

  const loadObjects = useCallback(async (force = false) => {
    if (!open || !baseline) return;
    const requestKey = `${baseline.id}:${perspective}`;
    if (
      !force
      && objectsRequestKeyRef.current === requestKey
      && objectsRequestRef.current
      && !objectsRequestRef.current.signal.aborted
    ) return;
    objectsRequestRef.current?.abort();
    const controller = new AbortController();
    objectsRequestRef.current = controller;
    objectsRequestKeyRef.current = requestKey;
    const generation = ++objectsGenerationRef.current;
    setObjectsLoading(true);
    try {
      const response = await apiRef.current.getBaselineComplianceObjects(
        baseline.id,
        {
          perspective,
          page: 1,
          page_size: -1,
        },
        { signal: controller.signal },
      );
      if (generation === objectsGenerationRef.current && !controller.signal.aborted) {
        setObjectsData(response);
        setSelectedId((current) => (
          current && response.items.some((item) => item.id === current)
            ? current
            : response.items[0]?.id
        ));
      }
    } catch {
      if (generation === objectsGenerationRef.current && !controller.signal.aborted) {
        setObjectsData(null);
        setSelectedId(undefined);
      }
    } finally {
      if (generation === objectsGenerationRef.current) {
        setObjectsLoading(false);
        objectsRequestRef.current = null;
        objectsRequestKeyRef.current = '';
      }
    }
  }, [baseline?.id, open, perspective]);

  const loadDetails = useCallback(async (force = false) => {
    if (!open || !baseline || !selectedId) {
      setDetailsData(null);
      return;
    }
    const requestKey = [
      baseline.id,
      perspective,
      selectedId,
      detailPage,
      detailPageSize,
      appliedDetailSearch,
      detailStatus || '',
    ].join(':');
    if (
      !force
      && detailsRequestKeyRef.current === requestKey
      && detailsRequestRef.current
      && !detailsRequestRef.current.signal.aborted
    ) return;
    detailsRequestRef.current?.abort();
    const controller = new AbortController();
    detailsRequestRef.current = controller;
    detailsRequestKeyRef.current = requestKey;
    const generation = ++detailsGenerationRef.current;
    setDetailsLoading(true);
    try {
      const response = await apiRef.current.getBaselineComplianceDetails(
        baseline.id,
        {
          perspective,
          selected_id: selectedId,
          page: detailPage,
          page_size: detailPageSize,
          search: appliedDetailSearch || undefined,
          status: detailStatus,
        },
        { signal: controller.signal },
      );
      if (generation === detailsGenerationRef.current && !controller.signal.aborted) {
        setDetailsData(response);
      }
    } catch {
      // 保留已展示的明细，让用户可以修改搜索条件或重试。
    } finally {
      if (generation === detailsGenerationRef.current) {
        setDetailsLoading(false);
        detailsRequestRef.current = null;
        detailsRequestKeyRef.current = '';
      }
    }
  }, [
    appliedDetailSearch,
    baseline?.id,
    detailPage,
    detailPageSize,
    detailStatus,
    open,
    perspective,
    selectedId,
  ]);

  useEffect(() => {
    void loadObjects();
  }, [loadObjects]);

  useEffect(() => {
    void loadDetails();
  }, [loadDetails]);

  useEffect(() => {
    if (open) return;
    objectsRequestRef.current?.abort();
    detailsRequestRef.current?.abort();
    setPerspective('host');
    setObjectsData(null);
    setDetailsData(null);
    setObjectSearch('');
    setDetailSearch('');
    setAppliedDetailSearch('');
    setDetailStatus(undefined);
    setSelectedId(undefined);
    setDetailPage(1);
    setSelectedDetailKeys([]);
  }, [open]);

  useEffect(() => {
    setSelectedDetailKeys([]);
  }, [
    appliedDetailSearch,
    detailPage,
    detailPageSize,
    detailStatus,
    perspective,
    selectedId,
  ]);

  const statusOptions = useMemo(() => (
    (['satisfied', 'missing', 'not_applicable', 'unknown', 'pending', 'evaluating', 'failed'] as BaselineComplianceResultStatus[])
      .map((status) => ({
        value: status,
        label: t(`patchManager.baseline.complianceDetail.status.${status}`),
      }))
  ), [t]);

  const handlePerspectiveChange = (key: string) => {
    objectsRequestRef.current?.abort();
    detailsRequestRef.current?.abort();
    setObjectsData(null);
    setDetailsData(null);
    setPerspective(key as BaselineCompliancePerspective);
    setSelectedId(undefined);
    setDetailPage(1);
    setDetailStatus(undefined);
    setObjectSearch('');
    setDetailSearch('');
    setAppliedDetailSearch('');
  };

  const selectObject = (id: number) => {
    if (id === selectedIdRef.current) return;
    selectedIdRef.current = id;
    setDetailsData(null);
    setSelectedId(id);
    setDetailPage(1);
  };

  const refreshDrawer = async () => {
    await Promise.allSettled([loadObjects(true), loadDetails(true)]);
  };

  const refreshAll = async () => {
    await Promise.allSettled([
      refreshDrawer(),
      Promise.resolve(onRefreshRef.current?.()),
    ]);
  };

  const assessNow = async () => {
    if (!baseline) return;
    setAssessing(true);
    try {
      const result = await apiRef.current.assessBaseline(baseline.id);
      message.success(t('patchManager.baseline.assessCreated', undefined, { count: result.host_count || 0 }));
      await Promise.resolve(onRefreshRef.current?.());
    } finally {
      setAssessing(false);
    }
  };

  const commonColumns: ColumnsType<ComplianceDetailRow> = [
    {
      title: t('patchManager.baseline.complianceDetail.assessmentStatus'),
      dataIndex: 'status',
      width: 150,
      render: (status: BaselineComplianceResultStatus) => (
        <><ResultTag status={status} /></>
      ),
    },
    {
      title: t('patchManager.baseline.complianceDetail.evidence'),
      dataIndex: 'evidence_display',
      width: 180,
      ellipsis: true,
    },
    {
      title: t('patchManager.baseline.complianceDetail.reason'),
      dataIndex: 'reason_display',
      width: 190,
      ellipsis: true,
    },
    {
      title: t('patchManager.baseline.complianceDetail.assessedAt'),
      dataIndex: 'evaluated_at_display',
      width: 165,
    },
  ];

  const hostColumns: ColumnsType<ComplianceDetailRow> = [
    {
      title: t('patchManager.baseline.complianceDetail.patch'),
      dataIndex: 'identifier',
      width: 125,
      fixed: 'left',
    },
    {
      title: t('patchManager.baseline.description'),
      dataIndex: 'title',
      width: 210,
      ellipsis: true,
    },
    {
      title: t('patchManager.severity'),
      dataIndex: 'severity',
      width: 95,
      render: (severity: BaselineComplianceHostDetail['severity']) => <><SeverityTag severity={severity} /></>,
    },
    {
      title: t('patchManager.baseline.complianceDetail.requirement'),
      dataIndex: 'condition',
      width: 210,
      ellipsis: true,
    },
    ...commonColumns,
  ];

  const patchColumns: ColumnsType<ComplianceDetailRow> = [
    {
      title: t('patchManager.baseline.complianceDetail.host'),
      dataIndex: 'target_name',
      width: 150,
      ellipsis: true,
      fixed: 'left',
    },
    { title: 'IP', dataIndex: 'target_ip', width: 130 },
    ...commonColumns,
  ];

  const normalizedObjectSearch = objectSearch.trim().toLocaleLowerCase();
  const objectItems = (objectsData?.items || []).filter((item) => {
    if (!normalizedObjectSearch) return true;
    if (perspective === 'host') {
      const host = item as BaselineComplianceHostObject;
      return [host.name, host.ip].some((value) => value.toLocaleLowerCase().includes(normalizedObjectSearch));
    }
    const patch = item as BaselineCompliancePatchObject;
    return [patch.identifier, patch.title, patch.condition]
      .some((value) => value.toLocaleLowerCase().includes(normalizedObjectSearch));
  });
  const selected = detailsData?.selected;
  const selectedHost = perspective === 'host' ? selected as BaselineComplianceHostObject | null : null;
  const selectedPatch = perspective === 'patch' ? selected as BaselineCompliancePatchObject | null : null;
  const detailRows: ComplianceDetailRow[] = (detailsData?.details.items || []).map((item) => ({
    ...item,
    evidence_display: formatComplianceEvidence(item.evidence),
    reason_display: item.reason || '—',
    evaluated_at_display: convertToLocalizedTime(item.evaluated_at) || '—',
  }));
  const detailRowKey = (row: ComplianceDetailRow) => perspective === 'host'
    ? String((row as BaselineComplianceHostDetail).requirement_id)
    : String((row as BaselineCompliancePatchDetail).target_id);
  const selectedDetailRows = detailRows.filter((row) => selectedDetailKeys.includes(detailRowKey(row)));

  const exportSelectedDetails = async () => {
    if (!selectedDetailRows.length || !baseline) return;
    setExporting(true);
    try {
      const workbook = buildBaselineComplianceWorkbook({
        perspective,
        rows: selectedDetailRows,
        translate: t,
        formatTime: convertToLocalizedTime,
      });
      const selectedObjectName = perspective === 'host'
        ? selectedHost?.name
        : selectedPatch?.identifier;
      const timestamp = new Date().toISOString().slice(0, 19).replace(/[-:T]/g, '');
      const filename = sanitizeExportFilename([
        t('patchManager.baseline.complianceDetail.title'),
        baseline.name,
        selectedObjectName,
        t('patchManager.risk.selected'),
        timestamp,
      ].filter(Boolean).join('-'));
      await downloadBaselineComplianceWorkbook(workbook, `${filename}.xlsx`);
      message.success(t('patchManager.risk.exportSelectedSucceeded'));
    } catch {
      message.error(t('common.exportFailed'));
    } finally {
      setExporting(false);
    }
  };

  return (
    <OperateDrawer
      title={t('patchManager.baseline.complianceDetail.title')}
      subTitle={baseline?.name}
      open={open}
      onClose={onClose}
      width={960}
      extra={(
        <Tooltip title={t('patchManager.refresh')}>
          <Button
            type="text"
            icon={<ReloadOutlined />}
            aria-label={t('patchManager.refresh')}
            onClick={() => void refreshAll()}
          />
        </Tooltip>
      )}
      bodyStyle={{ padding: 0, overflow: 'hidden' }}
    >
      <div className={styles.drawerLayout}>
        <div className={styles.tabsBar}>
          <Tabs
            activeKey={perspective}
            onChange={handlePerspectiveChange}
            tabBarExtraContent={(
              <PermissionWrapper requiredPermissions={['Add']} permissionPath="/patch-manager/risk-execution">
                <Popconfirm
                  title={t('patchManager.baseline.assessTitle')}
                  description={t('patchManager.baseline.assessConfirm', undefined, {
                    name: baseline?.name || '',
                    count: baseline?.bound_host_count || objectsData?.count || 0,
                  })}
                  okText={t('patchManager.baseline.confirmAssess')}
                  cancelText={t('patchManager.cancel')}
                  disabled={!baseline?.can_assess || assessing}
                  onConfirm={assessNow}
                >
                  <Tooltip title={!baseline?.can_assess ? baseline?.assess_disabled_reason : ''}>
                    <span>
                      <Button
                        type="link"
                        size="small"
                        loading={assessing}
                        disabled={!baseline?.can_assess}
                      >
                        {t('patchManager.dashboard.assessNow')}
                      </Button>
                    </span>
                  </Tooltip>
                </Popconfirm>
              </PermissionWrapper>
            )}
            items={[
              { key: 'host', label: t('patchManager.baseline.complianceDetail.hostPerspective') },
              { key: 'patch', label: t('patchManager.baseline.complianceDetail.patchPerspective') },
            ]}
          />
        </div>
        <div className={styles.drawerBody}>
          <aside className={styles.objectPane}>
            <Input.Search
              aria-label={perspective === 'host'
                ? t('patchManager.baseline.complianceDetail.searchHost')
                : t('patchManager.baseline.complianceDetail.objectSearch')}
              placeholder={perspective === 'host'
                ? t('patchManager.baseline.complianceDetail.searchHost')
                : t('patchManager.baseline.complianceDetail.objectSearch')}
              value={objectSearch}
              allowClear
              onChange={(event) => setObjectSearch(event.target.value)}
            />
            <div className={styles.objectList}>
              <Spin spinning={objectsLoading}>
                {objectItems.length ? objectItems.map((item) => {
                  const isHost = perspective === 'host';
                  const host = item as BaselineComplianceHostObject;
                  const patch = item as BaselineCompliancePatchObject;
                  const isSelected = selectedId === item.id;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      className={`${styles.objectItem} ${isSelected ? styles.objectItemSelected : ''}`}
                      style={{
                        '--status-border-color': getComplianceObjectBorderColor({
                          perspective,
                          complianceStatus: isHost ? host.compliance_status : undefined,
                          distribution: item.distribution,
                        }),
                      } as React.CSSProperties}
                      onClick={() => selectObject(item.id)}
                      aria-pressed={isSelected}
                    >
                      <EllipsisWithTooltip
                        className={styles.objectTitle}
                        text={isHost ? host.name : patch.identifier}
                      />
                      <div className={styles.objectMeta}>
                        {isHost ? (
                          <Space size={6}>
                            <ComplianceTag status={host.compliance_status} missing={host.missing_count} />
                            <span>{host.ip}</span>
                          </Space>
                        ) : (
                          <Space size={6}>
                            <SeverityTag severity={patch.severity} />
                            <EllipsisWithTooltip
                              className={styles.objectMetaText}
                              text={patch.title}
                            />
                          </Space>
                        )}
                      </div>
                    </button>
                  );
                }) : (
                  <CompactEmptyState
                    description={objectsLoading
                      ? t('patchManager.baseline.complianceDetail.loading')
                      : normalizedObjectSearch
                        ? t('patchManager.baseline.complianceDetail.noObjects')
                        : perspective === 'host'
                          ? t('patchManager.baseline.complianceDetail.noBoundHosts')
                          : t('patchManager.baseline.complianceDetail.noRequirements')}
                  />
                )}
              </Spin>
            </div>
          </aside>

          <section className={styles.detailPane}>
            {selected ? (
            <>
              <div className={styles.summarySection}>
                <div className={styles.detailHeader}>
                  <div className={styles.detailTitle}>
                    {perspective === 'host' ? selectedHost?.name : selectedPatch?.identifier}
                    <div className={styles.detailSubtitle}>
                      <span>
                        {perspective === 'host'
                          ? selectedHost?.ip || '—'
                          : selectedPatch?.title || '—'}
                      </span>
                      <DistributionTags items={selected.distribution} />
                    </div>
                  </div>
                  {perspective === 'host' && selectedHost && (
                    <ComplianceTag status={selectedHost.compliance_status} missing={selectedHost.missing_count} />
                  )}
                  {perspective === 'patch' && selectedPatch && <SeverityTag severity={selectedPatch.severity} />}
                </div>
                <FilterToolbar
                  align="start"
                  spacing="flush"
                  className={styles.toolbar}
                  contentClassName="flex w-full flex-wrap items-center gap-2"
                >
                  <Input.Search
                    aria-label={perspective === 'host'
                      ? t('patchManager.baseline.complianceDetail.detailSearch')
                      : t('patchManager.baseline.complianceDetail.searchHostIp')}
                    placeholder={perspective === 'host'
                      ? t('patchManager.baseline.complianceDetail.detailSearch')
                      : t('patchManager.baseline.complianceDetail.searchHostIp')}
                    value={detailSearch}
                    allowClear
                    className={styles.detailSearch}
                    onChange={(event) => setDetailSearch(event.target.value)}
                    onSearch={(value) => {
                      setAppliedDetailSearch(value);
                      setDetailPage(1);
                    }}
                  />
                  <Select
                    allowClear
                    placeholder={t('patchManager.baseline.complianceDetail.filterStatus')}
                    value={detailStatus}
                    options={statusOptions}
                    className={styles.statusSelect}
                    onChange={(value) => {
                      setDetailStatus(value);
                      setDetailPage(1);
                    }}
                  />
                </FilterToolbar>
              </div>
              <div className={styles.tableRegion}>
                <CustomTable<ComplianceDetailRow>
                  rowKey={detailRowKey}
                  size="small"
                  loading={detailsLoading}
                  dataSource={detailRows}
                  columns={perspective === 'host' ? hostColumns : patchColumns}
                  rowSelection={{
                    fixed: true,
                    selectedRowKeys: selectedDetailKeys,
                    onChange: setSelectedDetailKeys,
                  }}
                  scroll={{ x: perspective === 'host' ? 1330 : 965, y: 'calc(100vh - 430px)' }}
                  pagination={false}
                  locale={{ emptyText: <CompactEmptyState description={t('patchManager.baseline.complianceDetail.noDetails')} /> }}
                />
              </div>
              <div className={styles.detailPagination}>
                <Pagination
                  current={detailPage}
                  pageSize={detailPageSize}
                  total={detailsData?.details.count || 0}
                  showSizeChanger
                  showTotal={(total) => t('patchManager.common.totalItems', undefined, { count: total })}
                  onChange={(page, pageSize) => {
                    setDetailPage(page);
                    setDetailPageSize(pageSize);
                  }}
                />
              </div>
            </>
            ) : (
              <Spin spinning={objectsLoading || detailsLoading} style={{ margin: 'auto' }}>
                <CompactEmptyState description={t('patchManager.baseline.complianceDetail.noSelection')} />
              </Spin>
            )}
          </section>
        </div>
      </div>
    </OperateDrawer>
  );
}
