'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Button, Card, Select, Space, Spin, Table, Tag, Tooltip, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { InfoCircleOutlined, LinkOutlined, PlusOutlined } from '@ant-design/icons';
import AlarmDetailDrawer from '@/app/alarm/components/alarm-detail-drawer';
import DeclareIncident, {
  type DeclareIncidentProps,
} from '@/components/declare-incident';
import AlarmLevelIcon from '@/app/alarm/components/alarm-level-icon';
import CompactEmptyState from '@/components/compact-empty-state';
import EventLevelTag from '@/components/event-level-tag';
import SummaryMetricCard from '@/components/summary-metric-card';
import type { AlarmActionContextProps } from '@/app/alarm/components/alarm-action/types';
import type {
  AlarmDetailDrawerData,
  AlarmDetailDrawerRef,
  AlarmDetailEventItem,
  AlarmDetailLogItem,
  AlarmDetailLevelOption,
} from '@/app/alarm/components/alarm-detail-drawer';
import { useTranslation } from '@/utils/i18n';

const MATCH_REASON_COLORS: Record<string, string> = {
  关键事件: 'red',
  相同服务: 'orange',
  相同位置: 'blue',
  相同资源: 'cyan',
  相关指标: 'green',
  相关告警: 'default',
};

interface RelatedAlertIncidentItem {
  id: number;
  incident_id: string;
  title: string;
}

export interface RelatedAlertItem extends AlarmDetailDrawerData {
  id: number;
  alert_id: string;
  title: string;
  content: string;
  level: string;
  status: string;
  first_event_time: string | null;
  last_event_time: string | null;
  incidents: RelatedAlertIncidentItem[];
  similarity_score: number;
  match_reason: string;
  matched_dimensions: Record<string, string>;
  time_proximity: string;
}

export interface RelatedAlertsResponse {
  related_count: number;
  maybe_related_count: number;
  current_incidents: RelatedAlertIncidentItem[];
  items: RelatedAlertItem[];
}

const getDefaultSelectedRelatedAlertIds = (items: RelatedAlertItem[]) =>
  items
    .filter((item) => item.similarity_score >= 80 && !(item.incidents || []).length)
    .map((item) => item.id);

const getMatchedDimensionsText = (matchedDimensions: Record<string, string>) => {
  const entries = Object.entries(matchedDimensions || {});
  if (!entries.length) {
    return '--';
  }
  return entries.map(([key, value]) => `${key}: ${value}`).join(' / ');
};

interface RelatedAlertsPanelProps {
  alert: AlarmDetailDrawerData;
  levelOptions: AlarmDetailLevelOption[];
  alarmActionProps: AlarmActionContextProps;
  declareIncidentProps?: Omit<DeclareIncidentProps, 'rowData' | 'onSuccess'>;
  onRefresh?: () => void;
  fetchRelatedAlerts: (
    alertId: number,
    params?: { time_window?: number; limit?: number }
  ) => Promise<RelatedAlertsResponse>;
  addAlertsToIncidentAction: (
    incidentId: string,
    alertIds: number[]
  ) => Promise<any>;
  detailFetchEventList: (
    params: Record<string, unknown>
  ) => Promise<{ items?: AlarmDetailEventItem[]; count?: number }>;
  detailFetchLogList: (
    params: Record<string, unknown>
  ) => Promise<{ items?: AlarmDetailLogItem[] }>;
}

const RelatedAlertsPanel: React.FC<RelatedAlertsPanelProps> = ({
  alert,
  levelOptions,
  alarmActionProps,
  declareIncidentProps,
  onRefresh,
  fetchRelatedAlerts,
  addAlertsToIncidentAction,
  detailFetchEventList,
  detailFetchLogList,
}) => {
  const { t } = useTranslation();
  const detailRef = useRef<AlarmDetailDrawerRef>(null);
  const getRelatedAlertsRef = useRef(fetchRelatedAlerts);
  getRelatedAlertsRef.current = fetchRelatedAlerts;

  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [data, setData] = useState<RelatedAlertsResponse | null>(null);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [selectedCurrentIncidentId, setSelectedCurrentIncidentId] = useState<
    number | null
  >(null);
  const [showCurrentIncidentSelector, setShowCurrentIncidentSelector] =
    useState(false);

  useEffect(() => {
    let disposed = false;
    const run = async () => {
      if (!alert?.id) {
        setData(null);
        setSelectedIds([]);
        return;
      }
      setLoading(true);
      try {
        const response = await getRelatedAlertsRef.current(Number(alert.id), {
          time_window: 60,
          limit: 20,
        });
        if (disposed) {
          return;
        }
        setData(response);
        setSelectedIds(getDefaultSelectedRelatedAlertIds(response.items || []));
        setSelectedCurrentIncidentId(response.current_incidents?.[0]?.id || null);
      } finally {
        if (!disposed) {
          setLoading(false);
        }
      }
    };

    void run();
    return () => {
      disposed = true;
    };
  }, [alert?.id]);

  const selectedRows = useMemo(() => {
    const items = (data?.items || []).filter((item) => selectedIds.includes(item.id));
    return [
      alert,
      ...items.map((item) => ({
        ...item,
        incident_name: (item.incidents || [])
          .map((incident) => incident.title)
          .join(', '),
      })),
    ];
  }, [alert, data?.items, selectedIds]);

  const selectedCount = selectedIds.length;
  const currentIncidents = data?.current_incidents || [];
  const fallbackCurrentIncidentNames = alert?.incident_name
    ? String(alert.incident_name)
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean)
    : [];

  const reloadData = async () => {
    const response = await getRelatedAlertsRef.current(Number(alert.id), {
      time_window: 60,
      limit: 20,
    });
    setData(response);
    setSelectedIds(getDefaultSelectedRelatedAlertIds(response.items || []));
    setSelectedCurrentIncidentId(response.current_incidents?.[0]?.id || null);
    setShowCurrentIncidentSelector(false);
  };

  const handleAddToCurrentIncident = async () => {
    if (!selectedCurrentIncidentId || selectedIds.length === 0) {
      return;
    }
    setSubmitting(true);
    try {
      await addAlertsToIncidentAction(
        String(selectedCurrentIncidentId),
        selectedIds
      );
      message.success(t('alarmCommon.successOperate'));
      setShowCurrentIncidentSelector(false);
      onRefresh?.();
      await reloadData();
    } catch {
      message.error(t('alarmCommon.operateFailed'));
    } finally {
      setSubmitting(false);
    }
  };

  const handleOpenDetail = (item: RelatedAlertItem) => {
    detailRef.current?.showModal({
      title: item.title,
      form: item,
      type: '',
      defaultTab: 'baseInfo',
    });
  };

  const renderDeclareIncident = declareIncidentProps
    ? (nextAlert: any, context: { onSuccess: (result: any) => void }) => (
        <DeclareIncident
          rowData={[nextAlert]}
          onSuccess={context.onSuccess}
          {...declareIncidentProps}
        />
    )
    : undefined;

  const formatIncidentNames = (
    incidents: Array<{ title: string; incident_id: string }>
  ) => {
    if (!incidents.length) {
      return '--';
    }

    const visibleNames = incidents
      .slice(0, 2)
      .map((incident) => incident.title || incident.incident_id);
    const remainingCount = incidents.length - visibleNames.length;

    return remainingCount > 0
      ? `${visibleNames.join('、')} +${remainingCount}`
      : visibleNames.join('、');
  };

  const currentIncidentDisplayText = currentIncidents.length
    ? formatIncidentNames(currentIncidents)
    : fallbackCurrentIncidentNames.length
      ? fallbackCurrentIncidentNames.length > 2
        ? `${fallbackCurrentIncidentNames.slice(0, 2).join('、')} +${fallbackCurrentIncidentNames.length - 2}`
        : fallbackCurrentIncidentNames.join('、')
      : '--';

  const columns: ColumnsType<RelatedAlertItem> = [
    {
      title: t('alarms.alarmName', '告警名称'),
      dataIndex: 'title',
      key: 'title',
      render: (text: string) => (
        <span className="font-medium text-[var(--color-text-1)]">{text}</span>
      ),
    },
    {
      title: t('alarms.level', '级别'),
      dataIndex: 'level',
      key: 'level',
      render: (level: string) => {
        const target = levelOptions.find((item) => item.value === String(level));

        return (
          <EventLevelTag
            color={target?.color}
            label={target?.label || '--'}
            icon={<AlarmLevelIcon icon={target?.icon || ''} className="h-4 w-4" />}
          />
        );
      },
    },
    {
      title: t('alarms.similarity', '相似度'),
      dataIndex: 'similarity_score',
      key: 'similarity_score',
      render: (score: number) => `${score}%`,
    },
    {
      title: t('alarms.matchReason', '关联原因'),
      dataIndex: 'match_reason',
      key: 'match_reason',
      render: (reason: string, record: RelatedAlertItem) => (
        <Tooltip title={getMatchedDimensionsText(record.matched_dimensions || {})}>
          <Tag color={MATCH_REASON_COLORS[reason] || 'default'}>{reason}</Tag>
          <InfoCircleOutlined className="ml-1 text-xs text-[var(--color-text-2)]" />
        </Tooltip>
      ),
    },
    {
      title: t('common.actions', '操作'),
      key: 'actions',
      render: (_value, record) => (
        <div className="flex items-center gap-3 whitespace-nowrap">
          <Button
            type="link"
            size="small"
            className="px-0"
            onClick={() => handleOpenDetail(record)}
          >
            {t('common.view', '查看')}
          </Button>
        </div>
      ),
    },
  ];

  return (
    <Card
      title={t('alarms.relatedAlertsRecommend', '相关告警推荐')}
      size="small"
      className="h-full"
    >
      {loading ? (
        <div className="flex min-h-[280px] items-center justify-center">
          <Spin />
        </div>
      ) : !data?.items?.length ? (
        <CompactEmptyState description={t('alarms.noRelatedAlerts')} className="py-10" />
      ) : (
        <>
          <div className="space-y-5">
            <div className="grid gap-3 md:grid-cols-[180px_180px_minmax(0,1fr)]">
              <SummaryMetricCard
                label={t('alarms.clearlyRelated', '清晰相关')}
                value={data.related_count}
                valueColor="var(--color-danger)"
                className="p-4 shadow-sm"
                valueClassName="text-[36px] font-semibold"
                subtitleClassName="text-sm"
                minFontSize={24}
                maxFontSize={36}
              />
              <SummaryMetricCard
                label={t('alarms.maybeRelated', '可疑关联')}
                value={data.maybe_related_count}
                valueColor="var(--color-warning)"
                className="p-4 shadow-sm"
                valueClassName="text-[36px] font-semibold"
                subtitleClassName="text-sm"
                minFontSize={24}
                maxFontSize={36}
              />
              <SummaryMetricCard
                label={t('alarms.currentIncidentLabel', '已归属事故')}
                value={
                  <span className="inline-flex items-center gap-2">
                    <span>{currentIncidentDisplayText}</span>
                    {currentIncidentDisplayText !== '--' ? (
                      <span className="h-2 w-2 rounded-full bg-[var(--color-success)]" />
                    ) : null}
                  </span>
                }
                className="p-4 shadow-sm"
                valueClassName="text-base font-medium"
                minFontSize={16}
                maxFontSize={20}
              />
            </div>

            <div className="overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-1)] shadow-sm">
              <div className="flex flex-wrap items-center gap-3 border-b border-[var(--color-border)] bg-[var(--color-bg-2)] px-4 py-3">
                <div className="flex min-w-0 flex-1 flex-wrap items-center gap-3">
                  <div className="inline-flex items-center gap-2 rounded-md bg-[var(--color-primary-light)] px-3 py-2 text-sm font-medium text-[var(--color-primary)]">
                    <span className="inline-flex h-4 w-4 items-center justify-center rounded-sm bg-[var(--color-primary)] text-white">
                      ✓
                    </span>
                    <span>
                      {t(
                        'alarms.selectedRelatedAlerts',
                        '已选择 {count} 条相关告警',
                        { count: selectedCount }
                      )}
                    </span>
                  </div>
                  <span className="text-sm text-[var(--color-text-2)]">
                    {t('alarms.currentIncidentText', '当前事故')}:{' '}
                    {currentIncidentDisplayText}
                  </span>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  {currentIncidents.length ? (
                    showCurrentIncidentSelector ? (
                      <Space.Compact block={false}>
                        <Select
                          value={selectedCurrentIncidentId || undefined}
                          onChange={setSelectedCurrentIncidentId}
                          className="min-w-[240px]"
                          options={currentIncidents.map((incident) => ({
                            label: incident.title || incident.incident_id,
                            value: incident.id,
                          }))}
                        />
                        <Button
                          type="primary"
                          loading={submitting}
                          disabled={!selectedIds.length || !selectedCurrentIncidentId}
                          onClick={handleAddToCurrentIncident}
                        >
                          {t('common.confirm', '确认')}
                        </Button>
                      </Space.Compact>
                    ) : (
                      <Button
                        type="primary"
                        icon={<PlusOutlined />}
                        disabled={!selectedIds.length || !selectedCurrentIncidentId}
                        onClick={() => setShowCurrentIncidentSelector(true)}
                      >
                        {t('alarms.addToCurrentIncident', '添加到当前事故')}
                      </Button>
                    )
                  ) : null}

                  {declareIncidentProps ? (
                    <Tooltip title={t('alarms.linkToOtherIncidentTip')}>
                      <span>
                        <DeclareIncident
                          rowData={selectedRows}
                          onSuccess={() => {
                            message.success(t('alarmCommon.successOperate'));
                            onRefresh?.();
                            void reloadData();
                          }}
                          {...declareIncidentProps}
                        />
                      </span>
                    </Tooltip>
                  ) : null}
                </div>
              </div>

              <Table
                rowKey="id"
                dataSource={data.items}
                pagination={false}
                size="small"
                columns={columns}
                scroll={{ x: 920 }}
                rowSelection={{
                  selectedRowKeys: selectedIds,
                  onChange: (keys) => setSelectedIds(keys as number[]),
                  getCheckboxProps: (record) => ({
                    disabled: !!record.incidents?.length,
                  }),
                }}
              />
            </div>

            <Alert
              type="warning"
              showIcon
              icon={<LinkOutlined />}
              message={t('alarms.whyRelated')}
              description={
                <ul className="mb-0 list-disc space-y-1 pl-4 text-xs text-[var(--color-text-2)]">
                  <li>{t('alarms.whyRelatedService')}</li>
                  <li>{t('alarms.whyRelatedLocation')}</li>
                  <li>{t('alarms.whyRelatedResource')}</li>
                  <li>{t('alarms.whyRelatedTimeWindow')}</li>
                </ul>
              }
            />
          </div>
          <AlarmDetailDrawer
            ref={detailRef}
            fetchEventList={detailFetchEventList}
            fetchLogList={detailFetchLogList}
            levelOptions={levelOptions}
            handleAction={onRefresh}
            alarmActionProps={alarmActionProps}
            renderDeclareIncident={renderDeclareIncident}
            renderRelatedAlerts={(nextAlert, context) => (
              <RelatedAlertsPanel
                alert={nextAlert}
                levelOptions={levelOptions}
                alarmActionProps={alarmActionProps}
                declareIncidentProps={declareIncidentProps}
                onRefresh={context.onRefresh}
                fetchRelatedAlerts={fetchRelatedAlerts}
                addAlertsToIncidentAction={addAlertsToIncidentAction}
                detailFetchEventList={detailFetchEventList}
                detailFetchLogList={detailFetchLogList}
              />
            )}
          />
        </>
      )}
    </Card>
  );
};

export default RelatedAlertsPanel;
